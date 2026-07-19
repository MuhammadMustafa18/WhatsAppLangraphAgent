export default function LoadingScreen() {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-gray-900">
      <div className="text-center">
        <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-4 border-gray-600 border-t-blue-500" />
        <p className="text-sm text-gray-400">Starting...</p>
      </div>
    </div>
  );
}
