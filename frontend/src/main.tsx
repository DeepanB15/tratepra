import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { RangeProvider } from "./hooks/useRange";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <RangeProvider>
        <App />
      </RangeProvider>
    </BrowserRouter>
  </React.StrictMode>
);
