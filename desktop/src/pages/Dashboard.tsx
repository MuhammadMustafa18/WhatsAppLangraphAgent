export default function Dashboard() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-800 p-4 rounded-lg">
          <h2 className="text-gray-400 text-sm">Providers</h2>
          <p className="text-3xl font-bold">0</p>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <h2 className="text-gray-400 text-sm">Personas</h2>
          <p className="text-3xl font-bold">0</p>
        </div>
        <div className="bg-gray-800 p-4 rounded-lg">
          <h2 className="text-gray-400 text-sm">Connections</h2>
          <p className="text-3xl font-bold">0</p>
        </div>
      </div>
    </div>
  );
}
