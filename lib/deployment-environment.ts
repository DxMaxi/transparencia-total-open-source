/** Search exclusions are not an access-control boundary; editorial routes still require MFA. */
export function isNonPublicDeployment(env: Record<string, string | undefined> = process.env): boolean {
  return env.DEPLOYMENT_ENVIRONMENT === "staging" || env.VERCEL_ENV === "preview";
}
