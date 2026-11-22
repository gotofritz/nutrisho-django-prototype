import "@/styles/tokens.css";
import "@/styles/clipper.css";

import { DEFAULT_SCENE, SCENES } from "./scenes";
import "./preview.css";

const wanted = new URLSearchParams(window.location.search).get("scene");
const name = wanted !== null && wanted in SCENES ? wanted : DEFAULT_SCENE;
const scene = SCENES[name]!;

const picker = document.getElementById("scenes");
for (const [key, { label }] of Object.entries(SCENES)) {
  const link = document.createElement("a");
  link.href = `?scene=${key}`;
  link.textContent = label;
  if (key === name) link.setAttribute("aria-current", "page");
  picker?.append(link);
}

const target = document.getElementById("app");
if (target === null) throw new Error("preview: #app missing");
document.title = `Nutrisho clipper — ${scene.label}`;
scene.mount(target);
