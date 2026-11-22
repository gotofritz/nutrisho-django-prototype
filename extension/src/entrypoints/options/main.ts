import { mount } from "svelte";
import App from "./App.svelte";

// The site's look (plan 012, M12): its tokens and faces, then the clipper's rules.
import "@/styles/tokens.css";
import "@/styles/clipper.css";

const target = document.getElementById("app");
if (!target) throw new Error("options: #app missing");

export default mount(App, { target });
