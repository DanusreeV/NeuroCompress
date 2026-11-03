import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Compress from "./pages/Compress";
import Benchmark from "./pages/Benchmark";
import ModelLab from "./pages/ModelLab";
import Decompress from "./pages/Decompress";
import History from "./pages/History";
import About from "./pages/About";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/compress" element={<Compress />} />
        <Route path="/benchmark" element={<Benchmark />} />
        <Route path="/models" element={<ModelLab />} />
        <Route path="/decompress" element={<Decompress />} />
        <Route path="/history" element={<History />} />
        <Route path="/about" element={<About />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
