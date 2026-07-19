/**
 * Baileys WhatsApp Gateway — standalone sidecar binary.
 *
 * Spawned by Tauri alongside uvicorn. Provides:
 *   - HTTP POST /send-text   — Python backend calls this to send replies
 *   - HTTP GET  /health      — Tauri health-check
 *   - WebSocket /events      — React UI connects for QR codes + connection status
 *
 * Compile:  npm run build && npm run compile
 * Output:   baileys-sidecar.exe  (~40MB standalone, no Node needed)
 * Dev run:  npm run dev
 */

import { makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestWaWebVersion } from "@whiskeysockets/baileys";
import express from "express";
import { createServer } from "http";
import { WebSocketServer, WebSocket } from "ws";
import { Boom } from "@hapi/boom";
import QRCode from "qrcode";
import pino from "pino";

// ── Config ──────────────────────────────────────────────────────────────

const HTTP_PORT = parseInt(process.env.BAILEYS_PORT || "2786", 10);
const WS_PORT = HTTP_PORT + 1;
const AUTH_DIR = process.env.APP_DATA_DIR
  ? `${process.env.APP_DATA_DIR}/baileys-auth`
  : "./baileys-auth";
const BACKEND_URL = process.env.BACKEND_URL || "http://127.0.0.1:18234";

const logger = pino({ level: "info" });

// ── State ───────────────────────────────────────────────────────────────

type ConnectionStatus =
  | "disconnected"
  | "qr"
  | "connecting"
  | "connected";

let connectionStatus: ConnectionStatus = "disconnected";
let qrCodeData: string | null = null;
let wsClients: Set<WebSocket> = new Set();
let sock: ReturnType<typeof makeWASocket>;

// ── Broadcast ───────────────────────────────────────────────────────────

function broadcast(event: string, data: Record<string, unknown>) {
  const msg = JSON.stringify({ event, ...data });
  for (const ws of wsClients) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(msg);
    }
  }
}

// ── QR helper ───────────────────────────────────────────────────────────

function generateQR(qrString: string): string {
  return QRCode.toDataURL(qrString, { width: 600, margin: 4, color: { dark: "#000", light: "#FFF" } });
}

// ── WhatsApp socket lifecycle ───────────────────────────────────────────

async function startSocket() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);

  const { version } = await fetchLatestWaWebVersion();
  console.log("[baileys] Using WA Web version:", version);

  const newSock = makeWASocket({
    auth: state,
    version,
    logger,
    browser: ["Windows", "Chrome", "130"],
  });

  sock = newSock;

  newSock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    console.log("[baileys] connection.update:", JSON.stringify({ connection, hasQr: !!qr, hasError: !!lastDisconnect?.error }));

    if (qr) {
      qrCodeData = qr;
      connectionStatus = "qr";
      const qrImage = await generateQR(qr);
      broadcast("qr", { qrImage, qrData: qr });
      console.log("[baileys] QR code generated — scan with WhatsApp");
    }

    if (connection) {
      connectionStatus = connection as ConnectionStatus;
      broadcast("status", { status: connection });

      if (connection === "open") {
        qrCodeData = null;
        console.log("[baileys] WhatsApp connected!");
      }

      if (connection === "close") {
        if (lastDisconnect?.error) {
          const boom = lastDisconnect.error as Boom;
          console.log("[baileys] Disconnect error:", {
            statusCode: boom.output?.statusCode,
            message: boom.message,
            data: boom.data,
          });
        }

        const reason = lastDisconnect?.error
          ? (lastDisconnect.error as Boom).output?.statusCode
          : 0;

        if (reason === DisconnectReason.loggedOut) {
          console.log("[baileys] Logged out — QR scan needed");
          broadcast("status", { status: "loggedOut" });
          return;
        }

        console.log("[baileys] Disconnected (reason=%s), reconnecting in 2s...", reason);
        connectionStatus = "disconnected";
        setTimeout(() => startSocket(), 2000);
      }
    }
  });

  newSock.ev.on("messages.upsert", async ({ messages }) => {
    for (const msg of messages) {
      if (msg.key.fromMe) continue;

      const chatId = msg.key.remoteJid;
      const body =
        msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text ||
        "";

      if (!chatId || !body) continue;

      console.log("[baileys] ← incoming from %s: %s", chatId, body.slice(0, 80));

      try {
        const resp = await fetch(`${BACKEND_URL}/webhook`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            event: "message.received",
            payload: {
              id: msg.key.id,
              from: chatId,
              body,
              fromMe: false,
            },
          }),
        });

        if (!resp.ok) {
          console.warn(
            "[baileys] backend returned %s for message from %s",
            resp.status,
            chatId
          );
        }
      } catch (err) {
        console.error("[baileys] failed to forward message to backend:", err);
      }
    }
  });

  newSock.ev.on("creds.update", saveCreds);
}

// ── Main ────────────────────────────────────────────────────────────────

async function main() {
  const app = express();
  app.use(express.json());

  app.get("/health", (_req, res) => {
    res.json({
      status: "ok",
      connection: connectionStatus,
      hasQr: qrCodeData !== null,
    });
  });

  app.post("/send-text", async (req, res) => {
    const { chatId, text } = req.body;

    if (!chatId || !text) {
      res.status(400).json({ error: "chatId and text required" });
      return;
    }

    try {
      await sock.sendMessage(chatId, { text });
      console.log("[baileys] → sent to %s: %s", chatId, text.slice(0, 80));
      res.json({ status: "sent" });
    } catch (err) {
      console.error("[baileys] send failed:", err);
      res.status(500).json({ error: String(err) });
    }
  });

  app.get("/status", (_req, res) => {
    res.json({
      status: connectionStatus,
      jid: sock?.user?.id || null,
    });
  });

  const httpServer = createServer(app);
  httpServer.listen(HTTP_PORT, () => {
    console.log(
      "[baileys] HTTP server on port %d, WebSocket on port %d",
      HTTP_PORT,
      WS_PORT
    );
  });

  const wss = new WebSocketServer({ port: WS_PORT });

  wss.on("connection", (ws) => {
    wsClients.add(ws);
    console.log("[baileys] WebSocket client connected");

    ws.send(
      JSON.stringify({
        event: "status",
        status: connectionStatus,
      })
    );

    if (qrCodeData) {
      generateQR(qrCodeData).then((img) => {
        ws.send(JSON.stringify({ event: "qr", qrImage: img }));
      });
    }

    ws.on("close", () => {
      wsClients.delete(ws);
      console.log("[baileys] WebSocket client disconnected");
    });

    ws.on("error", () => {
      wsClients.delete(ws);
    });
  });

  process.on("SIGTERM", () => {
    console.log("[baileys] shutting down...");
    sock?.end(undefined);
    httpServer.close();
    wss.close();
    process.exit(0);
  });

  process.on("SIGINT", () => {
    console.log("[baileys] shutting down...");
    sock?.end(undefined);
    httpServer.close();
    wss.close();
    process.exit(0);
  });

  await startSocket();
}

main().catch((err) => {
  console.error("[baileys] fatal error:", err);
  process.exit(1);
});
