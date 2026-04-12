/*import express from "express";
import recommendationRoutes from "./routes/recommendationRoutes";
import cors from "cors";
const app = express();
const PORT = 3000;

app.use(express.json());
app.use(cors());
app.use("/api/recommendations", recommendationRoutes);
app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`);
});*/

import express from "express";
import cors from "cors";
import { connectRedis } from "./redis/client";
import eligibilityRoute from "./routes/eligibility";
import recommendationRoute from "./routes/recommendation";
import flatLookupRoute from "./routes/flatLookup";
import flatAmenitiesRoute from "./routes/flatAmenities";
import { startAdapters } from "./startAdapters";

async function startServer() {
  await connectRedis();
  startAdapters();

  const app = express();
  app.use(cors());
  app.use(express.json());

  app.use(eligibilityRoute);
  app.use(recommendationRoute);
  app.use(flatLookupRoute);
  app.use(flatAmenitiesRoute);

  const port = Number(process.env.PORT || 3000);

  app.listen(port, () => {
    console.log(`API running on port ${port}`);
  });
}

startServer().catch((err) => {
  console.error("Failed to start server:", err);
  process.exit(1);
});