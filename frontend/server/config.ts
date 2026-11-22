import "server-only";

export const API_URL = process.env.API_URL ?? "http://api:8000";
export const COOKIE = "challsmith_session";
// response headers the BFF passes back to the browser; everything else from the api is dropped
export const KEEP_HEADERS = ["content-type", "content-disposition", "content-length"];
