import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import TickerDetail from "./pages/TickerDetail";
import Reconciled from "./pages/Reconciled";
import Earnings from "./pages/Earnings";
import Macro from "./pages/Macro";
import Bonds from "./pages/Bonds";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/ticker/:symbol" element={<TickerDetail />} />
        <Route path="/reconcile/:symbol" element={<Reconciled />} />
        <Route path="/earnings" element={<Earnings />} />
        <Route path="/macro" element={<Macro />} />
        <Route path="/bonds" element={<Bonds />} />
      </Route>
    </Routes>
  );
}
