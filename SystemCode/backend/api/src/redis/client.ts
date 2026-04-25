import { createClient } from "redis";

export const redis = createClient({
  url: "redis://127.0.0.1:6379",
});

let connected = false;

redis.on("error", (err) => {
  console.error("Redis error:", err);
});

export async function connectRedis(): Promise<void> {
  if (connected) return;
  await redis.connect();
  connected = true;
}