import AppShell from "@/app-shell";
import ClerkAccess from "@/components/clerk-access";

function App() {
  return (
    <ClerkAccess>
      <AppShell />
    </ClerkAccess>
  );
}

export default App;
