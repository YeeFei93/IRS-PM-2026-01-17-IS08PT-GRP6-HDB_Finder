import { spawn, ChildProcess } from "child_process";
import path from "path";

declare global {
  var __eligibilityAdapterStarted__: boolean | undefined;
  var __eligibilityAdapterProcess__: ChildProcess | undefined;
}

export function startAdapters() {
  if (global.__eligibilityAdapterStarted__) {
    return;
  }

  const pythonBin = process.env.PYTHON_BIN || "python";
  const scriptPath = path.resolve(__dirname, "../../adapters/eligibility_adapter.py");

  const child = spawn(pythonBin, [scriptPath], {
    stdio: "inherit",
  });

  child.on("error", (err) => {
    console.error("Eligibility adapter failed to start:", err);
  });

  child.on("exit", (code) => {
    console.error(`Eligibility adapter exited with code ${code}`);
    global.__eligibilityAdapterStarted__ = false;
    global.__eligibilityAdapterProcess__ = undefined;
  });

  global.__eligibilityAdapterStarted__ = true;
  global.__eligibilityAdapterProcess__ = child;

  const stop = () => {
    if (global.__eligibilityAdapterProcess__) {
      global.__eligibilityAdapterProcess__.kill();
      global.__eligibilityAdapterProcess__ = undefined;
      global.__eligibilityAdapterStarted__ = false;
    }
  };

  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
}