import { create } from "zustand";

export type ConnectionStatus =
  | "disconnected"
  | "qr"
  | "connecting"
  | "connected"
  | "loggedOut";

interface WhatsAppState {
  /** Current connection status of the Baileys sidecar. */
  status: ConnectionStatus;
  /** Base64 data-URL of the QR code image (set when status === "qr"). */
  qrImage: string | null;
  /** Raw QR string (for debugging). */
  qrData: string | null;
  /** WhatsApp JID of the connected account (e.g. "92317...@s.whatsapp.net"). */
  jid: string | null;
  /** Whether the sidecar process is reachable. */
  sidecarOnline: boolean;

  setStatus: (status: ConnectionStatus) => void;
  setQr: (qrImage: string, qrData: string) => void;
  clearQr: () => void;
  setJid: (jid: string | null) => void;
  setSidecarOnline: (online: boolean) => void;
  reset: () => void;
}

const initialState = {
  status: "disconnected" as ConnectionStatus,
  qrImage: null,
  qrData: null,
  jid: null,
  sidecarOnline: false,
};

export const useWhatsAppStore = create<WhatsAppState>((set) => ({
  ...initialState,

  setStatus: (status) => set({ status }),

  setQr: (qrImage, qrData) =>
    set({ status: "qr", qrImage, qrData }),

  clearQr: () => set({ qrImage: null, qrData: null }),

  setJid: (jid) => set({ jid }),

  setSidecarOnline: (online) => set({ sidecarOnline: online }),

  reset: () => set(initialState),
}));
