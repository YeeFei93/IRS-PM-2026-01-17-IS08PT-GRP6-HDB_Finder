import { Router } from "express";
import { getRecommednations } from "../controllers/recommendationController";

const router = Router();

router.get("/", getRecommednations);

export default router;