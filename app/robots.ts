import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";
import { isNonPublicDeployment } from "@/lib/deployment-environment";

export default function robots(): MetadataRoute.Robots {
  if (isNonPublicDeployment()) {
    return { rules: { userAgent: "*", disallow: "/" } };
  }
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/admin/", "/auth/"],
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
  };
}
