import { Router, Request, Response } from "express";
import { callPythonService } from "../redis/requestReply";

const router = Router();

router.get("/api/favourites", async (_req: Request, res: Response) => {
  try {
    const result = await callPythonService(
      "queue:favourites",
      { action: "list" },
      30
    );

    if (result.status === "error") {
      return res.status(500).json(result);
    }

    return res.json(result);
  } catch (error) {
    return res.status(504).json({
      status: "error",
      error: error instanceof Error ? error.message : "Unknown error",
    });
  }
});

router.post("/api/favourites/toggle", async (req: Request, res: Response) => {
  try {
    const result = await callPythonService(
      "queue:favourites",
      { action: "toggle", ...req.body },
      30
    );

    if (result.status === "error") {
      return res.status(500).json(result);
    }

    return res.json(result);
  } catch (error) {
    return res.status(504).json({
      status: "error",
      error: error instanceof Error ? error.message : "Unknown error",
    });
  }
});

router.delete("/api/favourites/:resaleFlatId", async (req: Request, res: Response) => {
  try {
    const result = await callPythonService(
      "queue:favourites",
      {
        action: "remove",
        resale_flat_id: req.params.resaleFlatId,
      },
      30
    );

    if (result.status === "error") {
      return res.status(500).json(result);
    }

    return res.json(result);
  } catch (error) {
    return res.status(504).json({
      status: "error",
      error: error instanceof Error ? error.message : "Unknown error",
    });
  }
});

export default router;
