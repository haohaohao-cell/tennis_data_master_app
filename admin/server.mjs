import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const networkConfigPath = path.resolve(root, "..", "config", "network.json");

async function loadNetworkConfig() {
  let config;
  try {
    config = JSON.parse(await readFile(networkConfigPath, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") {
      throw new Error(
        `Network configuration file not found: ${networkConfigPath}\n\n` +
          "Copy config/network.example.json to config/network.json and configure the network settings for this machine.",
      );
    }
    throw new Error(`Invalid network configuration JSON: ${networkConfigPath}: ${error.message}`);
  }

  const apiBaseUrl = String(config?.public?.apiBaseUrl || "").trim().replace(/\/+$/, "");
  if (!apiBaseUrl) {
    throw new Error("network.json public.apiBaseUrl must be a non-empty URL");
  }

  const host = String(config?.admin?.host || "").trim();
  if (!host) {
    throw new Error("network.json is missing required field: admin.host");
  }
  const port = Number(config?.admin?.port);
  if (!Number.isInteger(port) || port <= 0 || port > 65535) {
    throw new Error("network.json admin.port must be an integer between 1 and 65535");
  }

  return { host, port, public: { apiBaseUrl } };
}

const networkConfig = await loadNetworkConfig();
const port = Number(process.env.ADMIN_PORT || process.env.PORT || networkConfig.port);
const listenHost = process.env.ADMIN_HOST || networkConfig.host;
if (!Number.isInteger(port) || port <= 0 || port > 65535) {
  throw new Error("Admin port must be an integer between 1 and 65535");
}

const mimeTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".json", "application/json; charset=utf-8"],
  [".svg", "image/svg+xml"],
]);

function resolveRequestPath(requestUrl) {
  const url = new URL(requestUrl, "http://admin.local");
  const pathname = decodeURIComponent(url.pathname);
  const requestedPath = pathname === "/" ? "index.html" : pathname.slice(1);
  const filePath = path.resolve(root, requestedPath);

  if (!filePath.startsWith(root)) {
    return null;
  }

  return filePath;
}

async function readIndex() {
  const indexPath = path.resolve(root, "index.html");
  const index = await readFile(indexPath, "utf8");
  const runtimeConfig = JSON.stringify({ public: networkConfig.public });
  return index.replace(
    "</head>",
    `<script>window.__TENNIS_NETWORK_CONFIG__=${runtimeConfig};</script></head>`,
  );
}

const server = createServer(async (request, response) => {
  if (!request.url) {
    response.writeHead(400);
    response.end("Bad request");
    return;
  }

  const filePath = resolveRequestPath(request.url);
  if (!filePath) {
    response.writeHead(403);
    response.end("Forbidden");
    return;
  }

  try {
    if (path.basename(filePath) === "index.html") {
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      response.end(await readIndex());
      return;
    }
    const body = await readFile(filePath);
    const contentType = mimeTypes.get(path.extname(filePath)) || "application/octet-stream";
    response.writeHead(200, { "content-type": contentType });
    response.end(body);
  } catch (error) {
    if (error.code === "ENOENT") {
      const indexBody = await readIndex();
      response.writeHead(200, { "content-type": "text/html; charset=utf-8" });
      response.end(indexBody);
      return;
    }

    response.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
    response.end("Admin dev server error");
  }
});

server.listen(port, listenHost, () => {
  console.log(`Tennis admin web running at http://${listenHost}:${port}`);
});
