import { Router, type IRouter } from "express";
import { GetGameHealthResponse } from "@workspace/api-zod";

const router: IRouter = Router();

router.get("/healthz", (_req, res) => {
  const data = GetGameHealthResponse.pick({ status: true }).parse({ status: "ok" });
  res.json(data);
});

export default router;
