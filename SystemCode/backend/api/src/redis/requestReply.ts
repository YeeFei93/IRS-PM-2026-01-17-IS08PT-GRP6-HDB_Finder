import { randomUUID } from "crypto";
import { redis } from "./client";

export type ServiceResponse<T = unknown> = {
  request_id: string;
  service: string;
  status: "success" | "error";
  result?: T;
  error?: string | null;
};

export async function callPythonService<TPayload, TResult>(
  queueName: string,
  payload: TPayload,
  timeoutSeconds = 15
): Promise<ServiceResponse<TResult>> {
  const requestId = randomUUID();
  const replyQueue = `reply:${requestId}`;

  const job = {
    request_id: requestId,
    reply_to: replyQueue,
    payload,
  };

  await redis.lPush(queueName, JSON.stringify(job));

  const reply = await redis.brPop(replyQueue, timeoutSeconds);

  if (!reply) {
    throw new Error(`Timeout waiting for ${queueName}`);
  }

  await redis.del(replyQueue);

  return JSON.parse(reply.element) as ServiceResponse<TResult>;
}