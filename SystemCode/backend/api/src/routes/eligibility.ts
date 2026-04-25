import { Router, Request, Response } from "express";
import { callPythonService } from "../redis/requestReply";

type EligibilityResult = {
  eligible: boolean;
  market: "both" | "resale_only" | "ineligible";
  warnings: string[];
  notes: string[];
};

const router = Router();

router.post("/api/eligibility-check", async (req: Request, res: Response) => {
  try {
    const result = await callPythonService<Record<string, unknown>, EligibilityResult>(
      "queue:eligibility",
      req.body,
      15
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