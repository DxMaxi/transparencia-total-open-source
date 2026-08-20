import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import {
  AI_PUBLIC_CAPABILITY,
  REQUIRED_PUBLIC_CAPABILITIES,
  verifyPublicApiCompatibility,
} from "../scripts/check-public-api-compatibility.mjs";
import { verifyNextArtifact } from "../scripts/verify-next-artifact.mjs";

function compatibleFetch(requestedUrls) {
  return async (url) => {
    requestedUrls.push(url);
    const path = new URL(url).pathname;
    if (path === "/api/v1/health") {
      return Response.json({
        status: "ok",
        version: "0.5.0-alpha.0",
        public_capabilities: [...REQUIRED_PUBLIC_CAPABILITIES, AI_PUBLIC_CAPABILITY],
      });
    }
    if (path === "/api/v1/public/parliament/explore") {
      return Response.json({
        kind: "votes",
        legislature: "XVII",
        sessions: [],
        initiatives: [],
        votes: [],
        total: 0,
        limit: 1,
        offset: 0,
        facets: {},
      });
    }
    if (path === "/api/v1/public/search") {
      const kinds = [
        "politicians",
        "parliament_sessions",
        "parliament_initiatives",
        "parliament_votes",
        "promises",
        "ai_explanations",
      ];
      return Response.json({
        query: "lei",
        legislature: "XVII",
        section_limit: 1,
        total_results: 0,
        available_sections: 6,
        unavailable_sections: 0,
        sections: kinds.map((kind) => ({
          kind,
          label: kind,
          availability: "AVAILABLE",
          total: 0,
          total_is_exact: true,
          items: [],
          view_all_href: "/",
          coverage_note: "Só projeções publicadas.",
        })),
        publication_rule: "Só projeções publicadas.",
        search_rule: "Não cria associações.",
      });
    }
    if (path === "/api/v1/public/parliament/publication-history") {
      return Response.json([]);
    }
    if (path === "/api/v1/public/ai-explanations") {
      return Response.json({
        items: [],
        total: 0,
        limit: 1,
        offset: 0,
        total_is_exact: true,
        publication_rule: "Só conteúdo publicado e revisto.",
      });
    }
    if (path === "/api/v1/public/ai-explanations/publication-history") {
      return Response.json([]);
    }
    return Response.json({ detail: "not found" }, { status: 404 });
  };
}

test("deployment preflight proves the V5.5 API contract before promoting the frontend", async () => {
  const requestedUrls = [];
  const result = await verifyPublicApiCompatibility("https://api.example.test", {
    fetchImpl: compatibleFetch(requestedUrls),
  });
  assert.equal(result.apiVersion, "0.5.0-alpha.0");
  assert.equal(result.mode, "CURRENT");
  assert.deepEqual(result.capabilities, [...REQUIRED_PUBLIC_CAPABILITIES, AI_PUBLIC_CAPABILITY]);
  assert.equal(requestedUrls.length, 6);
});

test("deployment preflight waits when a versioned API is missing global search", async () => {
  const fetchImpl = compatibleFetch([]);
  await assert.rejects(
    verifyPublicApiCompatibility("https://api.example.test", {
      fetchImpl: async (url, options) => {
        const path = new URL(url).pathname;
        if (path === "/api/v1/health") {
          return Response.json({
            status: "ok",
            version: "0.5.0-alpha.0",
            public_capabilities: [
              "parliament_explorer_v1",
              "parliament_publication_history_v1",
            ],
          });
        }
        return fetchImpl(url, options);
      },
    }),
    /global_search_v1/,
  );
});

test("a preview can render fail-closed before the production API gains global search", async () => {
  const requestedUrls = [];
  const fetchImpl = compatibleFetch(requestedUrls);
  const result = await verifyPublicApiCompatibility("https://api.example.test", {
    requireGlobalSearch: false,
    fetchImpl: async (url, options) => {
      const path = new URL(url).pathname;
      if (path === "/api/v1/health") {
        requestedUrls.push(url);
        return Response.json({
          status: "ok",
          version: "0.5.0-alpha.0",
          public_capabilities: [
            "parliament_explorer_v1",
            "parliament_publication_history_v1",
          ],
        });
      }
      return fetchImpl(url, options);
    },
  });

  assert.equal(result.mode, "CURRENT_AI_FAIL_CLOSED");
  assert.equal(
    requestedUrls.some((url) => new URL(url).pathname === "/api/v1/public/search"),
    false,
  );
});

test("deployment preflight rejects a declared V5.15 capability with broken routes", async () => {
  const fetchImpl = compatibleFetch([]);
  await assert.rejects(
    verifyPublicApiCompatibility("https://api.example.test", {
      fetchImpl: async (url, options) => {
        const path = new URL(url).pathname;
        if (path === "/api/v1/public/ai-explanations") {
          return Response.json({ detail: "not found" }, { status: 404 });
        }
        return fetchImpl(url, options);
      },
    }),
    /ai-explanations.*HTTP 404/,
  );
});

test("deployment preflight accepts V4 only through all reviewed compatibility routes", async () => {
  const fetchImpl = async (url) => {
    const path = new URL(url).pathname;
    if (path === "/api/v1/health") {
      return Response.json({ status: "ok", version: "0.4.0" });
    }
    if (path === "/api/v1/public/data-status") {
      return Response.json({
        counts: {
          parliament_sessions: 237,
          parliament_initiatives: 2100,
          parliament_votes: 2473,
        },
      });
    }
    return Response.json([]);
  };
  const result = await verifyPublicApiCompatibility("https://api.example.test", { fetchImpl });
  assert.equal(result.apiVersion, "0.4.0");
  assert.equal(result.mode, "LIMITED_READ_ONLY");
  assert.deepEqual(result.capabilities, []);
});

test("deployment preflight rejects V4 when a reviewed compatibility route is missing", async () => {
  const fetchImpl = async (url) => {
    const path = new URL(url).pathname;
    if (path === "/api/v1/health") return Response.json({ status: "ok", version: "0.4.0" });
    if (path === "/api/v1/public/data-status") {
      return Response.json({
        counts: {
          parliament_sessions: 237,
          parliament_initiatives: 2100,
          parliament_votes: 2473,
        },
      });
    }
    if (path.endsWith("/votes")) {
      return Response.json({ detail: "not found" }, { status: 404 });
    }
    return Response.json([]);
  };
  await assert.rejects(
    verifyPublicApiCompatibility("https://api.example.test", { fetchImpl }),
    /parliament\/votes.*HTTP 404/,
  );
});

test("deployment artifact contains the V5.5.1 through V5.18 public styles", async () => {
  const root = await mkdtemp(join(tmpdir(), "tt-v551-artifact-"));
  try {
    const chunks = join(root, ".next", "static", "chunks");
    await mkdir(chunks, { recursive: true });
    await writeFile(
      join(chunks, "public.css"),
      ".parliament-page--v551{}.parliament-search-form__primary{}" +
        ".parliament-coverage__facts{}.contact-channel--pending{}" +
        ".profile-coverage-grid{}.profile-declaration-list{}" +
        ".ai-publication-panel{}.ai-public-card-grid{}.ai-public-detail__hero{}" +
        ".global-search-box{}.global-search-result__proof{}",
      "utf8",
    );
    const result = await verifyNextArtifact(root);
    assert.equal(result.markers, 11);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("Vercel and CI both enforce the deployment artifact contract", async () => {
  const [vercel, workflow] = await Promise.all([
    readFile(new URL("../vercel.json", import.meta.url), "utf8"),
    readFile(new URL("../.github/workflows/ci.yml", import.meta.url), "utf8"),
  ]);
  assert.match(vercel, /npm run check:deployment-api/);
  assert.match(vercel, /npm run verify:next-artifact/);
  assert.match(workflow, /npm run verify:next-artifact/);
});
