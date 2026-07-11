import React from "react";
import { createRoot } from "react-dom/client";
import ChatUI from "./ChatUI.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ChatUI />
  </React.StrictMode>,
);
