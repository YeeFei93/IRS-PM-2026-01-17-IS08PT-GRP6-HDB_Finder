import { Router, Request, Response } from "express";
import { callPythonService } from "../redis/requestReply";

const router = Router();

router.post("/api/flat-parks", async (req: Request, res: Response) => {
  try {
    const result = await callPythonService(
      "queue:flat_parks",
      req.body,
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
