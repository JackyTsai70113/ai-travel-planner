import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  const aiTravelPlannerVolume = volume("ai-travel-planner-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "sfo", sizeMB: 500 });
  const aiTravelPlanner = service("ai-travel-planner", {
    source: github("JackyTsai70113/ai-travel-planner", { branch: "main", checkSuites: false, upstreamUrl: "https://github.com/JackyTsai70113/ai-travel-planner" }),
    replicas: { "sfo": 1 },
    build: { builder: "DOCKERFILE", dockerfilePath: "/Dockerfile" },
    deploy: { healthcheckPath: "/health", healthcheckTimeout: 120, restartPolicyType: "ON_FAILURE", restartPolicyMaxRetries: 10 },
    volumeMounts: { "/data": aiTravelPlannerVolume },
    env: { BEARER_TOKEN: preserve(), GOOGLE_MAPS_API_KEY: preserve(), OPENROUTESERVICE_API_KEY: preserve(), PUBLIC_URL: preserve(), YOUTUBE_API_KEY: preserve() },
  });

  return project("gregarious-warmth", {
    resources: [aiTravelPlanner, aiTravelPlannerVolume],
  });
});
