import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";

const normalizedPath = window.location.pathname.replace(/\/+$/, "") || "/";
const isUsecases = normalizedPath === "/usecases";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App replayMode={isUsecases} />
  </React.StrictMode>
);
