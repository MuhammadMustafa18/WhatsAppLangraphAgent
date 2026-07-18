export default function Connections() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Connections</h1>
      <div className="bg-gray-800 p-4 rounded-lg">
        <p className="text-gray-400">No connections configured yet.</p>
        <button className="mt-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded">
          Add Connection
        </button>
      </div>
    </div>
  );
}
