import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type DemoRole = "staff" | "manager" | "customer-c3";

const CUSTOMER_GET_ALLOWLIST = [
  /^\/customer\/(?:profile|catalog|orders|tickets|exchange-requests)$/,
  /^\/customer\/tickets\/[A-Za-z0-9-]+\/(?:context|messages)$/,
  /^\/customer\/exchange-requests\/[A-Za-z0-9-]+\/status$/,
  /^\/customer\/cart$/,
  /^\/customer\/checkout\/(?:preview|orders)$/,
  /^\/customer\/style\/anchors$/,
];
const CUSTOMER_POST_ALLOWLIST = [
  /^\/customer\/tickets$/,
  /^\/customer\/cart\/items$/,
  /^\/customer\/checkout\/confirm$/,
  /^\/customer\/checkout\/orders\/[A-Za-z0-9-]+\/simulate-payment$/,
  /^\/customer\/style\/budget$/,
  /^\/customer\/style\/three-looks$/,
  /^\/customer\/style\/rescue\/(?:analyze|recommend)$/,
  /^\/customer\/tickets\/[A-Za-z0-9-]+\/(?:chat|exchange-preview|exchange-request)$/,
  /^\/exchange-proposals\/[A-Za-z0-9-]+\/customer-confirm$/,
];
const CUSTOMER_ITEM_PATH = /^\/customer\/cart\/items\/[A-Za-z0-9-]+$/;
const GET_ALLOWLIST = [
  /^\/health$/,
  /^\/operations\/sandbox-orders$/,
  /^\/operations\/insights$/,
  /^\/operations\/manage\/(?:inventory|tickets)$/,
  /^\/operations\/manage\/tickets\/[A-Za-z0-9-]+\/activity$/,
  /^\/integrations\/storage\/status$/,
  /^\/integrations\/storage\/products\/[A-Za-z0-9-]+\/image$/,
  /^\/tickets$/,
  /^\/catalog$/,
  /^\/analytics\/overview$/,
  /^\/exchange-proposals$/,
  /^\/tickets\/[A-Za-z0-9-]+\/(?:context|messages)$/,
  /^\/orders\/[A-Za-z0-9-]+\/exchanges$/,
];
const POST_ALLOWLIST = [
  /^\/tickets\/[A-Za-z0-9-]+\/agent\/chat$/,
  /^\/tickets\/[A-Za-z0-9-]+\/exchange-check$/,
  /^\/tickets\/[A-Za-z0-9-]+\/exchange-proposals$/,
  /^\/exchange-proposals\/[A-Za-z0-9-]+\/(?:customer-confirm|approve|execute-local|verify-condition)$/,
];

function allowed(method: string, path: string, role: DemoRole): boolean {
  if (method === "POST" && role === "manager" &&
      /^\/integrations\/storage\/products\/[A-Za-z0-9-]+\/image$/.test(path)) return true;
  if (method === "PATCH" && role !== "customer-c3") {
    if (/^\/operations\/manage\/tickets\/[A-Za-z0-9-]+$/.test(path)) return true;
    return role === "manager" && /^\/operations\/manage\/(?:products|variants)\/[A-Za-z0-9-]+$/.test(path);
  }
  if (role === "customer-c3") {
    if (method === "GET") return CUSTOMER_GET_ALLOWLIST.some((r) => r.test(path));
    if (method === "POST") return CUSTOMER_POST_ALLOWLIST.some((r) => r.test(path));
    if (method === "PATCH" || method === "DELETE") return CUSTOMER_ITEM_PATH.test(path);
    return false;
  }
  if (method === "GET") return GET_ALLOWLIST.some((r) => r.test(path));
  if (!POST_ALLOWLIST.some((r) => r.test(path))) return false;
  if (path.endsWith("/customer-confirm")) return false;
  if (path.endsWith("/verify-condition")) return role === "staff";
  if (path.endsWith("/approve") || path.endsWith("/execute-local")) return role === "manager";
  return role === "staff";
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  // Credential selection is ONLY a local role simulation for synthetic data.
  // Do not enable this gateway on a public host. Real users require sessions/JWT.
  if (process.env.DEMO_UI_ENABLED !== "true") {
    return NextResponse.json({ detail: "Local demo proxy disabled" }, { status: 403 });
  }
  const { path } = await context.params;
  const pathName = `/${path.join("/")}`;
  // Only catalog searches may forward query parameters through the demo proxy.
  // The target host and path remain server-side allowlisted.
  const catalogQueryKeys = new Set([
    "q", "category", "size", "color", "min_price_cents", "max_price_cents", "in_stock",
  ]);
  const isCatalog = pathName === "/catalog" || pathName === "/customer/catalog";
  for (const key of request.nextUrl.searchParams.keys()) {
    if (!isCatalog || !catalogQueryKeys.has(key)) {
      return NextResponse.json({ detail: "Query parameter not permitted" }, { status: 400 });
    }
  }
  const role = request.headers.get("x-demo-role") as DemoRole | null;
  if (!role || !["staff", "manager", "customer-c3"].includes(role) || !allowed(request.method, pathName, role)) {
    return NextResponse.json({ detail: "Demo route or role not permitted" }, { status: 403 });
  }
  const tokens: Record<DemoRole, string | undefined> = {
    staff: process.env.DEMO_STAFF_TOKEN,
    manager: process.env.DEMO_MANAGER_TOKEN,
    "customer-c3": process.env.DEMO_CUSTOMER_C3_TOKEN,
  };
  const token = tokens[role];
  if (!token) return NextResponse.json({ detail: "Demo credentials not configured" }, { status: 503 });
  const rawBase = process.env.BACKEND_URL || "http://127.0.0.1:8000";
  // Prevent an untrusted host from being supplied through a client request.
  const base = new URL(rawBase);
  const safeHosts = ["127.0.0.1", "localhost", process.env.DOCKER_DEMO_BACKEND_HOST].filter(Boolean);
  if (!(safeHosts.includes(base.hostname) && ["http:", "https:"].includes(base.protocol))) {
    return NextResponse.json({ detail: "Only loopback backend is allowed in the local demo" }, { status: 503 });
  }
  const isRescueUpload = pathName === "/customer/style/rescue/analyze" && request.method === "POST";
  const isCatalogImageUpload = /^\/integrations\/storage\/products\/[A-Za-z0-9-]+\/image$/.test(pathName) && request.method === "POST";
  const isCatalogImageGet = /^\/integrations\/storage\/products\/[A-Za-z0-9-]+\/image$/.test(pathName) && request.method === "GET";
  let body: string | FormData | undefined;
  if (isRescueUpload || isCatalogImageUpload) {
    // Allow only a single small image from the synthetic customer role.
    const form = await request.formData();
    const image = form.get("image");
    if (!(image instanceof File) || !["image/jpeg", "image/png", "image/webp"].includes(image.type) || image.size === 0 || image.size > 4 * 1024 * 1024) {
      return NextResponse.json({detail: "Upload a JPEG, PNG or WebP photo smaller than 4MB"}, {status: 413});
    }
    const outgoing = new FormData();
    outgoing.append("image", image, isRescueUpload ? "owned-item.jpg" : "catalog.jpg");
    body = outgoing;
  } else if (request.method === "POST" || request.method === "PATCH") {
    const incomingBody = await request.text();
    if (incomingBody.length > 16000) return NextResponse.json({ detail: "Request too large" }, { status: 413 });
    try { JSON.parse(incomingBody); } catch { return NextResponse.json({ detail: "Expected JSON body" }, { status: 400 }); }
    body = incomingBody;
  }
  try {
    const target = new URL(pathName, base);
    if (isCatalog) target.search = request.nextUrl.search;
    const upstream = await fetch(target, {
      method: request.method,
      headers: isRescueUpload || isCatalogImageUpload ? { "X-Demo-Token": token } : { "X-Demo-Token": token, "Content-Type": "application/json" },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(90000),
    });
    if (isCatalogImageGet && upstream.ok) {
      const image = await upstream.arrayBuffer();
      return new NextResponse(image, { status: upstream.status, headers: {
        "Content-Type": "image/jpeg", "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
      } });
    }
    const payload = await upstream.text();
    return new NextResponse(payload, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") || "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return NextResponse.json({ detail: "Backend unavailable. Start FastAPI on port 8000." }, { status: 503 });
  }
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}

export async function PATCH(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
export async function DELETE(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  return proxy(request, context);
}
