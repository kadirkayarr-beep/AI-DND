import {
  setAuthTokenGetter,
  setProtectedRequestCredentials,
} from "@workspace/api-client-react/custom-fetch";

import { nextAccountClient, type AccountBoundary } from "./account-session.ts";

const LOCAL_PLAY_IDENTITY = "local-owner:local-play";
// Not a secret and not an identity: the shared client needs a bearer value, and the local
// server ignores it. A Clerk server rejects it, so a stray local UI stays locked out.
const LOCAL_PLAY_BEARER = "local-play";

export function startLocalPlaySession(): AccountBoundary {
  setProtectedRequestCredentials("omit");
  setAuthTokenGetter(() => Promise.resolve(LOCAL_PLAY_BEARER));
  return nextAccountClient(null, LOCAL_PLAY_IDENTITY);
}
