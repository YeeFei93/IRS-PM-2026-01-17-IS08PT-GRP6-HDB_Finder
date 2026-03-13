import express from "express";
import recommendationRoutes from "./routes/recommendationRoutes";
import cors from "cors";
const app = express();
const PORT = 3000;

app.use(express.json());
app.use(cors());
app.use("/api/recommendations", recommendationRoutes);
app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});