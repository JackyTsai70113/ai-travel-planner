import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const aiTravellerVolume = volume("ai-traveller-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 500 });
  const aiTraveller = service("ai-traveller", {
    source: github("JackyTsai70113/ai-travel-planner", { branch: "main", checkSuites: false, upstreamUrl: "https://github.com/JackyTsai70113/ai-travel-planner" }),
    replicas: { "sfo": 1 },
    build: {
      builder: "DOCKERFILE",
      dockerfilePath: "/Dockerfile",
      watchPatterns: [
        "Dockerfile",
        "requirements-mcp.txt",
        "requirements-mcp-server.txt",
        "src/**",
        "trips/**",
      ],
    },
    deploy: { healthcheckPath: "/health", healthcheckTimeout: 120 },
    volumeMounts: { "/data": aiTravellerVolume },
    env: { BEARER_TOKEN: preserve(), GITHUB_PAGES_BASE_URL: preserve(), GITHUB_PAGES_BRANCH: preserve(), GITHUB_REPOSITORY: preserve(), GITHUB_TOKEN: preserve(), GOOGLE_MAPS_API_KEY: preserve(), OPENROUTESERVICE_API_KEY: preserve(), PUBLIC_URL: preserve(), YOUTUBE_API_KEY: preserve() },
  });

  return project("ai-traveller", {
    resources: [aiTraveller, aiTravellerVolume],
  });
});
