import { useEffect } from "react";
import { Link, NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Today } from "./pages/Today";
import { Build } from "./pages/Build";
import { QuizPage } from "./pages/Quiz";
import { Result } from "./pages/Result";
import { Review } from "./pages/Review";
import { Console } from "./pages/Console";
import { ThemeToggle } from "./components/ThemeToggle";

function ScrollTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export function App() {
  return (
    <div className="app">
      <ScrollTop />
      <header className="topbar">
        <Link to="/" className="brand">
          考点<span className="brand-en">kaodian</span>
        </Link>
        <nav className="nav">
          <NavLink to="/" end>
            今天
          </NavLink>
          <NavLink to="/console">控制台</NavLink>
          <NavLink to="/build">组卷</NavLink>
          <NavLink to="/review">复习</NavLink>
        </nav>
        <div className="topbar-actions">
          <span className="topbar-note">Agent 协作 · v0.1</span>
          <ThemeToggle />
        </div>
      </header>

      <main className="shell">
        <Routes>
          <Route path="/" element={<Today />} />
          <Route path="/console" element={<Console />} />
          <Route path="/build" element={<Build />} />
          <Route path="/quiz/:quizId" element={<QuizPage />} />
          <Route path="/result/:attemptId" element={<Result />} />
          <Route path="/review" element={<Review />} />
          <Route path="*" element={<Today />} />
        </Routes>
      </main>

      <footer className="footer">
        <span>考点 · 考纲驱动的刷题台</span>
        <span>数据存在你自己的机器上</span>
      </footer>
    </div>
  );
}