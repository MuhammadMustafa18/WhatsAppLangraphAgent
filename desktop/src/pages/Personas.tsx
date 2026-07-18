export default function Personas() {
  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Personas</h1>
      <div className="bg-gray-800 p-4 rounded-lg">
        <p className="text-gray-400">No personas configured yet.</p>
        <button className="mt-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded">
          Add Persona
        </button>
      </div>
    </div>
  );
}
