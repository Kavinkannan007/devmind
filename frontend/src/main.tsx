import {
  StrictMode,
  createContext,
  useContext,
  useEffect,
  useState,
} from "react";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useParams,
} from "react-router-dom";
import type { Session } from "@supabase/supabase-js";
import { supabase } from "./api";
import { Landing, Auth, Repositories, Profile } from "./pages";
import { Workspace } from "./workspace";
import { Loading } from "./ui";
import "./style.css";
const AuthContext = createContext<Session | null>(null);
export const useSession = () => useContext(AuthContext);
function Guard({ children }: { children: React.ReactNode }) {
  return useSession() ? children : <Navigate replace to="/auth" />;
}
function ScopedWorkspace() {
  const { id } = useParams();
  return <Workspace key={id} />;
}
function App() {
  const [session, setSession] = useState<Session | null>(null),
    [ready, setReady] = useState(!supabase);
  useEffect(() => {
    if (!supabase) return;
    const { data } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s);
      setReady(true);
    });
    return () => data.subscription.unsubscribe();
  }, []);
  if (!ready) return <Loading label="Restoring session" />;
  return (
    <AuthContext.Provider key={session?.user.id ?? "guest"} value={session}>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route
          path="/profile"
          element={
            <Guard>
              <Profile />
            </Guard>
          }
        />
        <Route path="/auth" element={<Auth />} />
        <Route
          path="/repositories"
          element={
            <Guard>
              <Repositories />
            </Guard>
          }
        />
        <Route
          path="/repositories/:id/*"
          element={
            <Guard>
              <ScopedWorkspace />
            </Guard>
          }
        />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
    </AuthContext.Provider>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
