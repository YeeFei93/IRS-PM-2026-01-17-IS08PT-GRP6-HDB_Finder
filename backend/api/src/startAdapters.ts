import { spawn, ChildProcess } from "child_process";
import path from "path";

declare global {
  var __adaptersStarted__: boolean | undefined;
  var __adapterProcesses__: ChildProcess[] | undefined;
}

export function startAdapters() {
  if (global.__adaptersStarted__) {
    return;
  }

  const pythonBin = process.env.PYTHON_BIN || "python";

  const adapterConfigs = [
    {
      name: "eligibility",
      script: "../../adapters/eligibility_adapter.py",
    },
    {
      name: "recommendation",
      script: "../../adapters/recommendation_adapter.py",
    },
    {
      name: "flat_lookup",
      script: "../../adapters/flat_lookup_adapter.py",
    },
    {
      name: "flat_amenities",
      script: "../../adapters/flat_amenities_adapter.py",
    },
  ];

  const processes: ChildProcess[] = [];

  for (const adapter of adapterConfigs) {
    const scriptPath = path.resolve(__dirname, adapter.script);

    const child = spawn(pythonBin, [scriptPath], {
      stdio: "inherit",
    });

    child.on("error", (err) => {
      console.error(`${adapter.name} adapter failed to start:`, err);
    });

    child.on("exit", (code) => {
      console.error(`${adapter.name} adapter exited with code ${code}`);
    });

    processes.push(child);
    console.log(`Started adapter: ${adapter.name}`);
  }

  global.__adaptersStarted__ = true;
  global.__adapterProcesses__ = processes;

  const stop = () => {
    if (global.__adapterProcesses__) {
      for (const proc of global.__adapterProcesses__) {
        proc.kill();
      }
    }

    global.__adapterProcesses__ = undefined;
    global.__adaptersStarted__ = false;
  };

  process.once("SIGINT", stop);
  process.once("SIGTERM", stop);
}