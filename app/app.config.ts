import fs from "node:fs";
import path from "node:path";
import type { ConfigContext, ExpoConfig } from "expo/config";

type NetworkConfig = {
  public?: {
    apiBaseUrl?: string;
  };
};

const networkConfigPath = path.resolve(__dirname, "..", "config", "network.json");

function loadNetworkConfig(): NetworkConfig {
  if (!fs.existsSync(networkConfigPath)) {
    throw new Error(
      `Network configuration file not found: ${networkConfigPath}\n\n` +
        "Copy config/network.example.json to config/network.json and configure the network settings for this machine.",
    );
  }

  let config: NetworkConfig;
  try {
    config = JSON.parse(fs.readFileSync(networkConfigPath, "utf8")) as NetworkConfig;
  } catch (error) {
    throw new Error(`Invalid network configuration JSON: ${networkConfigPath}: ${String(error)}`);
  }

  const apiBaseUrl = config.public?.apiBaseUrl?.trim().replace(/\/+$/, "");
  if (!apiBaseUrl) {
    throw new Error("network.json public.apiBaseUrl must be a non-empty URL");
  }

  return { public: { apiBaseUrl } };
}

export default ({ config }: ConfigContext): ExpoConfig => {
  const network = loadNetworkConfig();
  return {
    ...config,
    name: config.name ?? "app",
    slug: config.slug ?? "app",
    extra: {
      ...config.extra,
      network: {
        public: network.public,
      },
    },
  };
};
