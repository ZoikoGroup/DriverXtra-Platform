"use client";

/**
 * R1 Commercial Control Plane — admin console (Master Architecture v1.0 §15 "Commercial Admin").
 *
 * Basic functional UI for SKUs, rate schedules, party role profiles, country gates, non-binding
 * quote previews, issued quotes and the event outbox. All rules are enforced by the backend; this
 * view only collects input and displays results. Money is entered and shown via integer minor units.
 */

import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  fetchAllPages,
  CommercialSku,
  CommercialRateSchedule,
  PartyRoleProfile,
  CountryGate,
  CommercialQuote,
  CommercialQuotePreview,
  OutboxEventRecord,
} from "@/lib/api/client";
import {
  CURRENCY_EXPONENTS,
  currencyExponent,
  formatBasisPoints,
  formatMinor,
  parseMajorToMinor,
  parsePercentToBps,
} from "@/lib/money";
import {
  Landmark,
  Tags,
  Percent,
  Users,
  Globe2,
  Calculator,
  FileText,
  Radio,
  Plus,
  X,
  RefreshCw,
  ShieldAlert,
  Lock,
  Unlock,
  AlertCircle,
  Loader2,
  History,
} from "lucide-react";

// ---------------------------------------------------------------------------
// Controlled vocabularies (mirror apps/commercial/choices.py)
// ---------------------------------------------------------------------------

const VERTICALS = ["VEHICLES", "PARTS", "SERVICES", "EV", "ROADSIDE", "FLEET", "B2B", "ENTERPRISE_API", "ADVERTISING", "FINANCE_INSURANCE"];
const FAMILIES = ["ADVERTISING", "COMMERCE", "SUBSCRIPTION", "REFERRAL", "REGULATED", "API", "DATA", "MARKETING", "LOYALTY", "PAYMENT"];
const REVENUE_CODES = [
  "ADV-01", "ADV-02", "ADV-03", "ADV-04", "COM-01", "COM-02", "COM-03", "COM-04", "SUB-01", "SUB-02", "SUB-03",
  "SUB-04", "SUB-05", "REF-01", "REF-02", "REG-01", "REG-02", "API-01", "DAT-01", "MKT-01", "LOY-01", "FIN-01",
];
const FEE_BASES = ["FLAT_PER_UNIT", "PERCENT_OF_BASE", "RECURRING_FLAT", "PER_ACCEPTED_LEAD", "PER_ACTIVE_ASSET", "USAGE_METERED", "CUSTOM_CONTRACT"];
const ENTITLEMENTS = ["NONE", "LISTING", "INVENTORY_SLOT", "SEAT", "ASSET", "SITE", "API_QUOTA", "CAMPAIGN"];
const INTERVALS = ["ONE_TIME", "PER_EVENT", "MONTHLY", "ANNUAL"];
const PAYER_ROLES = ["BUYER", "PRIVATE_SELLER", "DEALER", "SUPPLIER", "WORKSHOP", "EV_PARTNER", "FLEET", "OEM_ENTERPRISE", "FINANCIAL_PARTNER", "ADVERTISER"];
const CAPABILITIES = ["DISCOVERY", "LEAD_CAPTURE", "BINDING_QUOTE", "SUBSCRIPTION_BILLING", "REGULATED_REFERRAL"];
const PROFILE_TYPES = ["ADVERTISING_ONLY", "SOFTWARE_ONLY", "FACILITATED_ORDER", "DISCLOSED_AGENT", "REGULATED_INTRODUCER", "CROSS_BORDER_ORCHESTRATOR", "PRINCIPAL_SELLER"];
const SELLER_OF_RECORD = ["THIRD_PARTY_SELLER", "PLATFORM", "NONE"];
const PERFORMERS = ["THIRD_PARTY_PROVIDER", "PLATFORM", "NONE"];
const PLATFORM_ROLES = ["ADVERTISING_PUBLISHER", "SOFTWARE_PROVIDER", "MARKETPLACE_FACILITATOR", "DISCLOSED_AGENT", "INTRODUCER", "ORCHESTRATOR", "PRINCIPAL"];
const PAYMENT_ROLES = ["NONE", "PSP_DIRECT_SETTLEMENT", "PSP_FACILITATED_SPLIT", "OFF_PLATFORM", "SUBSCRIPTION_BILLING", "PSP_CONDITIONAL_PAYOUT", "PARTNER_REGULATED"];
const TAX_PARTIES = ["SELLER", "PLATFORM", "BUYER_REVERSE_CHARGE", "DEEMED_SUPPLIER_PLATFORM"];
const INVOICE_ISSUERS = ["SELLER", "PLATFORM", "PSP", "PARTNER"];
const CURRENCIES = Object.keys(CURRENCY_EXPONENTS).sort();
const FLAT_BASES = new Set(["FLAT_PER_UNIT", "RECURRING_FLAT", "PER_ACCEPTED_LEAD", "PER_ACTIVE_ASSET"]);

const CATALOGUE_TRANSITIONS: Record<string, string[]> = {
  DRAFT: ["ILLUSTRATIVE", "APPROVED", "RETIRED"],
  ILLUSTRATIVE: ["DRAFT", "APPROVED", "RETIRED"],
  APPROVED: ["RETIRED"],
  RETIRED: [],
};
const PROFILE_TRANSITIONS: Record<string, string[]> = { DRAFT: ["APPROVED", "RETIRED"], APPROVED: ["RETIRED"], RETIRED: [] };
const EVIDENCE_STEPS = new Set(["LEGALLY_REVIEWED", "PARTNER_VERIFIED", "FINANCE_SIGNED", "TECHNICAL_REHEARSED"]);

type PanelId = "skus" | "rates" | "profiles" | "gates" | "preview" | "quotes" | "outbox";

// ---------------------------------------------------------------------------
// Shared helpers & small components
// ---------------------------------------------------------------------------

function errorText(err: unknown): string {
  if (err instanceof ApiError) {
    const details = err.details && typeof err.details === "object" && !Array.isArray(err.details)
      ? (err.details as Record<string, unknown>)
      : null;
    const detail = details && typeof details.detail === "string" ? details.detail : null;
    const rule = details && typeof details.rule === "string" ? details.rule : null;
    if (detail) return rule ? `${detail} [${rule}]` : detail;
    return err.message;
  }
  return err instanceof Error ? err.message : "Unexpected error.";
}

function toIso(localValue: string): string | null {
  if (!localValue) return null;
  const date = new Date(localValue);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

function useLoader<T>(loader: () => Promise<T[]>) {
  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(async () => {
    try {
      setItems(await loader());
      setError(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setLoading(false);
    }
  }, [loader]);

  useEffect(() => {
    let ignore = false;
    Promise.resolve().then(() => {
      if (!ignore) void run();
    });
    return () => {
      ignore = true;
    };
  }, [run]);

  const reload = useCallback(() => {
    setLoading(true);
    void run();
  }, [run]);

  return { items, loading, error, reload };
}

const STATUS_STYLES: Record<string, string> = {
  DRAFT: "bg-slate-100 text-slate-700 border-slate-200",
  ILLUSTRATIVE: "bg-amber-50 text-amber-800 border-amber-200",
  APPROVED: "bg-emerald-50 text-emerald-800 border-emerald-200",
  RETIRED: "bg-slate-50 text-slate-400 border-slate-200",
  ENABLED: "bg-emerald-50 text-emerald-800 border-emerald-200",
  SUSPENDED: "bg-rose-50 text-rose-700 border-rose-200",
  WITHDRAWN: "bg-slate-50 text-slate-400 border-slate-200",
  ISSUED: "bg-sky-50 text-sky-800 border-sky-200",
  ACCEPTED: "bg-emerald-50 text-emerald-800 border-emerald-200",
  EXPIRED: "bg-slate-50 text-slate-500 border-slate-200",
  PENDING: "bg-amber-50 text-amber-800 border-amber-200",
  PUBLISHED: "bg-emerald-50 text-emerald-800 border-emerald-200",
  FAILED: "bg-rose-50 text-rose-700 border-rose-200",
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] || "bg-indigo-50 text-indigo-800 border-indigo-200";
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md border text-[10px] font-bold tracking-wide ${style}`}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

function ErrorBanner({ message, onRetry }: { message: string | null; onRetry?: () => void }) {
  if (!message) return null;
  return (
    <div className="flex items-start gap-2 p-3 rounded-xl border border-rose-200 bg-rose-50 text-rose-800 text-xs">
      <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
      <span className="flex-1">{message}</span>
      {onRetry && (
        <button onClick={onRetry} className="font-bold underline">
          Retry
        </button>
      )}
    </div>
  );
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="flex flex-col gap-1 text-[11px] font-bold text-slate-600">
      {label}
      {children}
      {hint && <span className="font-normal text-slate-400">{hint}</span>}
    </label>
  );
}

const inputClass =
  "h-9 px-2.5 rounded-lg border border-slate-200 bg-white text-xs font-normal text-slate-900 focus:outline-none focus:ring-2 focus:ring-amber-300";

function Select({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: string[] }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={inputClass}>
      {options.map((option) => (
        <option key={option} value={option}>
          {option}
        </option>
      ))}
    </select>
  );
}

function PanelHeader({
  title,
  subtitle,
  onCreate,
  createLabel,
  onReload,
}: {
  title: string;
  subtitle: string;
  onCreate?: () => void;
  createLabel?: string;
  onReload: () => void;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h3 className="text-sm font-black text-slate-950">{title}</h3>
        <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>
      </div>
      <div className="flex items-center gap-2">
        <button onClick={onReload} className="h-8 px-3 rounded-lg border border-slate-200 text-xs font-bold text-slate-600 hover:bg-slate-50 flex items-center gap-1">
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
        {onCreate && (
          <button onClick={onCreate} className="h-8 px-3 rounded-lg bg-slate-950 text-white text-xs font-bold flex items-center gap-1">
            <Plus className="w-3.5 h-3.5" /> {createLabel}
          </button>
        )}
      </div>
    </div>
  );
}

function TableShell({ loading, empty, children }: { loading: boolean; empty: boolean; children: React.ReactNode }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-xs text-slate-500">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading…
      </div>
    );
  }
  if (empty) {
    return <div className="py-10 text-center text-xs text-slate-500">Nothing here yet.</div>;
  }
  return <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">{children}</div>;
}

const th = "px-3 py-2 text-left text-[10px] font-black uppercase tracking-wide text-slate-500 bg-slate-50 border-b border-slate-200";
const td = "px-3 py-2 text-xs text-slate-700 border-b border-slate-100 align-top";

// ---------------------------------------------------------------------------
// Transition dialog
// ---------------------------------------------------------------------------

interface TransitionRequest {
  title: string;
  options: string[];
  mode: "catalogue" | "gate";
  submit: (payload: { to_status: string; reason: string; approval_reference: string; evidence_reference: string }) => Promise<unknown>;
}

function TransitionDialog({ request, onClose, onDone }: { request: TransitionRequest; onClose: () => void; onDone: () => void }) {
  const [toStatus, setToStatus] = useState(request.options[0] || "");
  const [reason, setReason] = useState("");
  const [approvalReference, setApprovalReference] = useState("");
  const [evidenceReference, setEvidenceReference] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const needsApproval = request.mode === "catalogue" && toStatus === "APPROVED";
  const needsEvidence = request.mode === "gate" && EVIDENCE_STEPS.has(toStatus);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await request.submit({ to_status: toStatus, reason, approval_reference: approvalReference, evidence_reference: evidenceReference });
      onDone();
    } catch (err) {
      setError(errorText(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-2xl w-full max-w-md p-5 space-y-3 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between">
          <h4 className="text-sm font-black text-slate-950">{request.title}</h4>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600" aria-label="Close">
            <X className="w-4 h-4" />
          </button>
        </div>
        {request.options.length === 0 ? (
          <p className="text-xs text-slate-500">No further transitions are available from the current status.</p>
        ) : (
          <>
            <Field label="New status">
              <Select value={toStatus} onChange={setToStatus} options={request.options} />
            </Field>
            <Field label="Reason (recorded in the audit trail)">
              <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2} className={`${inputClass} h-auto py-2`} />
            </Field>
            {needsApproval && (
              <Field label="Approval reference" hint="CFO / commercial / legal approval ticket. You cannot approve items you authored.">
                <input value={approvalReference} onChange={(e) => setApprovalReference(e.target.value)} className={inputClass} />
              </Field>
            )}
            {needsEvidence && (
              <Field label="Evidence reference" hint="Memo, contract, sign-off or rehearsal record for this step.">
                <input value={evidenceReference} onChange={(e) => setEvidenceReference(e.target.value)} className={inputClass} />
              </Field>
            )}
            {request.mode === "gate" && toStatus === "ENABLED" && (
              <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2">
                Enabling opens this market. It requires a tax schedule, currencies, an approved role profile, and a different
                person from whoever recorded finance sign-off. Regulated gates cannot be enabled in R1.
              </p>
            )}
            <ErrorBanner message={error} />
            <div className="flex justify-end gap-2">
              <button onClick={onClose} className="h-9 px-4 rounded-lg border border-slate-200 text-xs font-bold text-slate-600">
                Cancel
              </button>
              <button
                onClick={submit}
                disabled={submitting || !toStatus}
                className="h-9 px-4 rounded-lg bg-slate-950 text-white text-xs font-bold disabled:opacity-50"
              >
                {submitting ? "Saving…" : "Confirm"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SKU catalogue
// ---------------------------------------------------------------------------

function SkuPanel({ openTransition }: { openTransition: (req: TransitionRequest, reload: () => void) => void }) {
  const [statusFilter, setStatusFilter] = useState("");
  const loader = useCallback(
    () => fetchAllPages<CommercialSku>(`/commercial/admin/skus/${statusFilter ? `?status=${statusFilter}` : ""}`),
    [statusFilter]
  );
  const { items, loading, error, reload } = useLoader(loader);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    sku_code: "", name: "", family: "SUBSCRIPTION", revenue_code: "SUB-01", vertical: "VEHICLES", fee_basis: "RECURRING_FLAT",
    entitlement_type: "NONE", billing_interval: "MONTHLY", illustrative_band_note: "", description: "",
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const create = async () => {
    setSaving(true);
    setFormError(null);
    try {
      await api.commercial.createSku(form);
      setShowForm(false);
      setForm((f) => ({ ...f, sku_code: "", name: "", illustrative_band_note: "", description: "" }));
      reload();
    } catch (err) {
      setFormError(errorText(err));
    } finally {
      setSaving(false);
    }
  };

  const newVersion = async (sku: CommercialSku) => {
    setActionError(null);
    try {
      await api.commercial.newSkuVersion(sku.id);
      reload();
    } catch (err) {
      setActionError(errorText(err));
    }
  };

  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  return (
    <div className="space-y-3">
      <PanelHeader
        title="SKU catalogue"
        subtitle="New SKUs are always DRAFT. Illustrative bands are planning notes only and never used to price."
        onCreate={() => setShowForm((v) => !v)}
        createLabel="New SKU"
        onReload={reload}
      />
      {showForm && (
        <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="SKU code"><input value={form.sku_code} onChange={(e) => set("sku_code")(e.target.value)} placeholder="DX-DEAL-GROWTH" className={inputClass} /></Field>
          <Field label="Name"><input value={form.name} onChange={(e) => set("name")(e.target.value)} className={inputClass} /></Field>
          <Field label="Family"><Select value={form.family} onChange={set("family")} options={FAMILIES} /></Field>
          <Field label="Revenue code"><Select value={form.revenue_code} onChange={set("revenue_code")} options={REVENUE_CODES} /></Field>
          <Field label="Vertical"><Select value={form.vertical} onChange={set("vertical")} options={VERTICALS} /></Field>
          <Field label="Fee basis"><Select value={form.fee_basis} onChange={set("fee_basis")} options={FEE_BASES} /></Field>
          <Field label="Entitlement"><Select value={form.entitlement_type} onChange={set("entitlement_type")} options={ENTITLEMENTS} /></Field>
          <Field label="Billing interval"><Select value={form.billing_interval} onChange={set("billing_interval")} options={INTERVALS} /></Field>
          <Field label="Illustrative band note"><input value={form.illustrative_band_note} onChange={(e) => set("illustrative_band_note")(e.target.value)} placeholder="Planning-only text" className={inputClass} /></Field>
          <div className="md:col-span-3"><Field label="Description"><input value={form.description} onChange={(e) => set("description")(e.target.value)} className={inputClass} /></Field></div>
          <div className="md:col-span-3 flex items-center justify-between gap-3">
            <ErrorBanner message={formError} />
            <button onClick={create} disabled={saving} className="h-9 px-4 rounded-lg bg-slate-950 text-white text-xs font-bold disabled:opacity-50 ml-auto">
              {saving ? "Creating…" : "Create draft SKU"}
            </button>
          </div>
        </div>
      )}
      <div className="flex items-center gap-2 text-xs">
        <span className="font-bold text-slate-500">Status</span>
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className={inputClass}>
          <option value="">All</option>
          {Object.keys(CATALOGUE_TRANSITIONS).map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </div>
      <ErrorBanner message={error || actionError} onRetry={error ? reload : undefined} />
      <TableShell loading={loading} empty={!items.length}>
        <table className="w-full">
          <thead>
            <tr>
              <th className={th}>SKU</th><th className={th}>Name</th><th className={th}>Revenue / vertical</th>
              <th className={th}>Fee basis</th><th className={th}>Status</th><th className={th}>Illustrative note</th><th className={th}></th>
            </tr>
          </thead>
          <tbody>
            {items.map((sku) => (
              <tr key={sku.id}>
                <td className={td}>
                  <div className="font-bold text-slate-900">{sku.sku_code}</div>
                  <div className="text-[10px] text-slate-400">v{sku.version}</div>
                </td>
                <td className={td}>{sku.name}</td>
                <td className={td}>{sku.revenue_code}<div className="text-[10px] text-slate-400">{sku.vertical}</div></td>
                <td className={td}>{sku.fee_basis}<div className="text-[10px] text-slate-400">{sku.billing_interval}</div></td>
                <td className={td}>
                  <div className="flex flex-col gap-1 items-start">
                    <StatusBadge status={sku.status} />
                    {sku.is_regulated && (
                      <span className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-700"><ShieldAlert className="w-3 h-3" /> Regulated / gated</span>
                    )}
                  </div>
                </td>
                <td className={`${td} max-w-[220px] text-slate-500`}>{sku.illustrative_band_note || "—"}</td>
                <td className={`${td} whitespace-nowrap`}>
                  <div className="flex gap-1.5">
                    <button
                      disabled={!CATALOGUE_TRANSITIONS[sku.status]?.length}
                      onClick={() => openTransition({
                        title: `Change status — ${sku.sku_code} v${sku.version}`,
                        options: CATALOGUE_TRANSITIONS[sku.status] || [],
                        mode: "catalogue",
                        submit: (p) => api.commercial.transitionSku(sku.id, { to_status: p.to_status, reason: p.reason, approval_reference: p.approval_reference }),
                      }, reload)}
                      className="h-7 px-2.5 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                    >
                      Status
                    </button>
                    <button onClick={() => newVersion(sku)} className="h-7 px-2.5 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-50">
                      New version
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableShell>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rate schedules
// ---------------------------------------------------------------------------

function RatePanel({ openTransition }: { openTransition: (req: TransitionRequest, reload: () => void) => void }) {
  const loader = useCallback(() => fetchAllPages<CommercialRateSchedule>("/commercial/admin/rate-schedules/"), []);
  const { items, loading, error, reload } = useLoader(loader);
  const skuLoader = useCallback(() => fetchAllPages<CommercialSku>("/commercial/admin/skus/"), []);
  const { items: skus } = useLoader(skuLoader);
  const pricedSkus = useMemo(
    () => skus.filter((s) => s.status !== "RETIRED" && (FLAT_BASES.has(s.fee_basis) || s.fee_basis === "PERCENT_OF_BASE")),
    [skus]
  );

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    sku: "", name: "", country_code: "", currency: "USD", payer_role: "DEALER", plan_code: "", priority: "100",
    effective_from: "", effective_to: "", amount: "", percentage: "", min_fee: "", max_fee: "",
  });
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const selectedSku = pricedSkus.find((s) => s.id === form.sku);
  const isPercent = selectedSku?.fee_basis === "PERCENT_OF_BASE";
  const exponent = currencyExponent(form.currency);

  const create = async () => {
    setFormError(null);
    if (!selectedSku) {
      setFormError("Choose a SKU.");
      return;
    }
    const effectiveFrom = toIso(form.effective_from);
    if (!effectiveFrom) {
      setFormError("Effective from is required.");
      return;
    }
    let payloadAmounts: { flat_amount_minor?: number | null; percentage_bps?: number | null; min_fee_minor?: number | null; max_fee_minor?: number | null };
    try {
      payloadAmounts = {
        ...(isPercent ? { percentage_bps: parsePercentToBps(form.percentage) } : { flat_amount_minor: parseMajorToMinor(form.amount, exponent) }),
        min_fee_minor: parseMajorToMinor(form.min_fee, exponent),
        max_fee_minor: parseMajorToMinor(form.max_fee, exponent),
      };
    } catch (err) {
      setFormError(err instanceof Error ? err.message : "Invalid amount.");
      return;
    }
    setSaving(true);
    try {
      await api.commercial.createRate({
        sku: selectedSku.id,
        name: form.name,
        country_code: form.country_code,
        currency: form.currency,
        payer_role: form.payer_role,
        plan_code: form.plan_code,
        priority: Number(form.priority) || 100,
        effective_from: effectiveFrom,
        effective_to: toIso(form.effective_to),
        ...payloadAmounts,
      });
      setShowForm(false);
      reload();
    } catch (err) {
      setFormError(errorText(err));
    } finally {
      setSaving(false);
    }
  };

  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const describeRate = (rate: CommercialRateSchedule) => {
    const main = rate.percentage_bps !== null
      ? formatBasisPoints(rate.percentage_bps)
      : formatMinor(rate.flat_amount_minor, rate.currency, rate.currency_exponent);
    const bounds = [
      rate.min_fee_minor !== null ? `min ${formatMinor(rate.min_fee_minor, rate.currency, rate.currency_exponent)}` : "",
      rate.max_fee_minor !== null ? `max ${formatMinor(rate.max_fee_minor, rate.currency, rate.currency_exponent)}` : "",
    ].filter(Boolean).join(" · ");
    return { main, bounds };
  };

  return (
    <div className="space-y-3">
      <PanelHeader
        title="Rate schedules"
        subtitle="Effective-dated, scoped by market × currency × payer × plan. Approval is prospective only and needs an approved SKU."
        onCreate={() => setShowForm((v) => !v)}
        createLabel="New rate"
        onReload={reload}
      />
      {showForm && (
        <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 grid grid-cols-1 md:grid-cols-4 gap-3">
          <Field label="SKU">
            <select value={form.sku} onChange={(e) => set("sku")(e.target.value)} className={inputClass}>
              <option value="">Select…</option>
              {pricedSkus.map((s) => <option key={s.id} value={s.id}>{s.sku_code} v{s.version} ({s.status})</option>)}
            </select>
          </Field>
          <Field label="Name"><input value={form.name} onChange={(e) => set("name")(e.target.value)} className={inputClass} /></Field>
          <Field label="Country (ISO-2)"><input value={form.country_code} onChange={(e) => set("country_code")(e.target.value.toUpperCase())} maxLength={2} className={inputClass} /></Field>
          <Field label="Currency"><Select value={form.currency} onChange={set("currency")} options={CURRENCIES} /></Field>
          <Field label="Payer role"><Select value={form.payer_role} onChange={set("payer_role")} options={PAYER_ROLES} /></Field>
          <Field label="Plan code (optional)"><input value={form.plan_code} onChange={(e) => set("plan_code")(e.target.value.toUpperCase())} className={inputClass} /></Field>
          <Field label="Priority"><input value={form.priority} onChange={(e) => set("priority")(e.target.value.replace(/\D/g, ""))} className={inputClass} /></Field>
          {isPercent ? (
            <Field label="Percentage" hint="e.g. 8 or 8.5 (stored as basis points)">
              <input value={form.percentage} onChange={(e) => set("percentage")(e.target.value)} className={inputClass} />
            </Field>
          ) : (
            <Field label={`Amount (${form.currency})`} hint={`Up to ${exponent} decimal place(s); stored in minor units`}>
              <input value={form.amount} onChange={(e) => set("amount")(e.target.value)} className={inputClass} />
            </Field>
          )}
          <Field label="Effective from"><input type="datetime-local" value={form.effective_from} onChange={(e) => set("effective_from")(e.target.value)} className={inputClass} /></Field>
          <Field label="Effective to (optional)"><input type="datetime-local" value={form.effective_to} onChange={(e) => set("effective_to")(e.target.value)} className={inputClass} /></Field>
          <Field label="Min fee (optional)"><input value={form.min_fee} onChange={(e) => set("min_fee")(e.target.value)} className={inputClass} /></Field>
          <Field label="Max fee (optional)"><input value={form.max_fee} onChange={(e) => set("max_fee")(e.target.value)} className={inputClass} /></Field>
          <div className="md:col-span-4 flex items-center justify-between gap-3">
            <ErrorBanner message={formError} />
            <button onClick={create} disabled={saving} className="h-9 px-4 rounded-lg bg-slate-950 text-white text-xs font-bold disabled:opacity-50 ml-auto">
              {saving ? "Creating…" : "Create draft rate"}
            </button>
          </div>
        </div>
      )}
      <ErrorBanner message={error} onRetry={reload} />
      <TableShell loading={loading} empty={!items.length}>
        <table className="w-full">
          <thead>
            <tr>
              <th className={th}>Rate</th><th className={th}>SKU</th><th className={th}>Scope</th><th className={th}>Amount</th>
              <th className={th}>Effective</th><th className={th}>Status</th><th className={th}></th>
            </tr>
          </thead>
          <tbody>
            {items.map((rate) => {
              const { main, bounds } = describeRate(rate);
              return (
                <tr key={rate.id}>
                  <td className={td}><div className="font-bold text-slate-900">{rate.name}</div><div className="text-[10px] text-slate-400">priority {rate.priority}</div></td>
                  <td className={td}>{rate.sku_code} v{rate.sku_version}<div className="text-[10px] text-slate-400">{rate.fee_basis}</div></td>
                  <td className={td}>{rate.country_code} · {rate.currency}<div className="text-[10px] text-slate-400">{rate.payer_role}{rate.plan_code ? ` · ${rate.plan_code}` : ""}</div></td>
                  <td className={td}><div className="font-bold">{main}</div>{bounds && <div className="text-[10px] text-slate-400">{bounds}</div>}</td>
                  <td className={td}>{formatDate(rate.effective_from)}<div className="text-[10px] text-slate-400">to {rate.effective_to ? formatDate(rate.effective_to) : "open-ended"}</div></td>
                  <td className={td}><StatusBadge status={rate.status} /></td>
                  <td className={td}>
                    <button
                      disabled={!CATALOGUE_TRANSITIONS[rate.status]?.length}
                      onClick={() => openTransition({
                        title: `Change status — ${rate.name}`,
                        options: CATALOGUE_TRANSITIONS[rate.status] || [],
                        mode: "catalogue",
                        submit: (p) => api.commercial.transitionRate(rate.id, { to_status: p.to_status, reason: p.reason, approval_reference: p.approval_reference }),
                      }, reload)}
                      className="h-7 px-2.5 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                    >
                      Status
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </TableShell>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Party role profiles
// ---------------------------------------------------------------------------

function RoleProfilePanel({ openTransition }: { openTransition: (req: TransitionRequest, reload: () => void) => void }) {
  const loader = useCallback(() => fetchAllPages<PartyRoleProfile>("/commercial/admin/role-profiles/"), []);
  const { items, loading, error, reload } = useLoader(loader);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    code: "", name: "", profile_type: "SOFTWARE_ONLY", country_code: "", vertical: "VEHICLES", seller_of_record: "PLATFORM",
    service_performer: "PLATFORM", platform_role: "SOFTWARE_PROVIDER", payment_role: "SUBSCRIPTION_BILLING", tax_party: "PLATFORM",
    invoice_issuer: "PLATFORM", legal_memo_reference: "", effective_from: "", effective_to: "",
  });
  const [licensed, setLicensed] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const create = async () => {
    setFormError(null);
    const effectiveFrom = toIso(form.effective_from);
    if (!effectiveFrom) {
      setFormError("Effective from is required.");
      return;
    }
    setSaving(true);
    try {
      await api.commercial.createRoleProfile({
        ...form,
        effective_from: effectiveFrom,
        effective_to: toIso(form.effective_to),
        licensed_partner_required: licensed,
      });
      setShowForm(false);
      reload();
    } catch (err) {
      setFormError(errorText(err));
    } finally {
      setSaving(false);
    }
  };

  const newVersion = async (profile: PartyRoleProfile) => {
    setActionError(null);
    try {
      await api.commercial.newRoleProfileVersion(profile.id);
      reload();
    } catch (err) {
      setActionError(errorText(err));
    }
  };

  return (
    <div className="space-y-3">
      <PanelHeader
        title="Party role profiles"
        subtitle="Who is seller of record, performer, payment role, tax party and invoice issuer — per market and vertical (§2, §9)."
        onCreate={() => setShowForm((v) => !v)}
        createLabel="New profile"
        onReload={reload}
      />
      {showForm && (
        <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 grid grid-cols-1 md:grid-cols-4 gap-3">
          <Field label="Code"><input value={form.code} onChange={(e) => set("code")(e.target.value.toUpperCase())} className={inputClass} /></Field>
          <Field label="Name"><input value={form.name} onChange={(e) => set("name")(e.target.value)} className={inputClass} /></Field>
          <Field label="Country (ISO-2)"><input value={form.country_code} onChange={(e) => set("country_code")(e.target.value.toUpperCase())} maxLength={2} className={inputClass} /></Field>
          <Field label="Vertical"><Select value={form.vertical} onChange={set("vertical")} options={VERTICALS} /></Field>
          <Field label="Profile type"><Select value={form.profile_type} onChange={set("profile_type")} options={PROFILE_TYPES} /></Field>
          <Field label="Seller of record"><Select value={form.seller_of_record} onChange={set("seller_of_record")} options={SELLER_OF_RECORD} /></Field>
          <Field label="Service performer"><Select value={form.service_performer} onChange={set("service_performer")} options={PERFORMERS} /></Field>
          <Field label="Platform role"><Select value={form.platform_role} onChange={set("platform_role")} options={PLATFORM_ROLES} /></Field>
          <Field label="Payment role"><Select value={form.payment_role} onChange={set("payment_role")} options={PAYMENT_ROLES} /></Field>
          <Field label="Tax party"><Select value={form.tax_party} onChange={set("tax_party")} options={TAX_PARTIES} /></Field>
          <Field label="Invoice issuer"><Select value={form.invoice_issuer} onChange={set("invoice_issuer")} options={INVOICE_ISSUERS} /></Field>
          <Field label="Legal memo reference"><input value={form.legal_memo_reference} onChange={(e) => set("legal_memo_reference")(e.target.value)} className={inputClass} /></Field>
          <Field label="Effective from"><input type="datetime-local" value={form.effective_from} onChange={(e) => set("effective_from")(e.target.value)} className={inputClass} /></Field>
          <Field label="Effective to (optional)"><input type="datetime-local" value={form.effective_to} onChange={(e) => set("effective_to")(e.target.value)} className={inputClass} /></Field>
          <label className="flex items-center gap-2 text-[11px] font-bold text-slate-600 mt-5">
            <input type="checkbox" checked={licensed} onChange={(e) => setLicensed(e.target.checked)} /> Licensed partner required
          </label>
          <div className="md:col-span-4 flex items-center justify-between gap-3">
            <ErrorBanner message={formError} />
            <button onClick={create} disabled={saving} className="h-9 px-4 rounded-lg bg-slate-950 text-white text-xs font-bold disabled:opacity-50 ml-auto">
              {saving ? "Creating…" : "Create draft profile"}
            </button>
          </div>
        </div>
      )}
      <ErrorBanner message={error || actionError} onRetry={error ? reload : undefined} />
      <TableShell loading={loading} empty={!items.length}>
        <table className="w-full">
          <thead>
            <tr>
              <th className={th}>Profile</th><th className={th}>Scope</th><th className={th}>Roles</th>
              <th className={th}>Effective</th><th className={th}>Status</th><th className={th}></th>
            </tr>
          </thead>
          <tbody>
            {items.map((profile) => (
              <tr key={profile.id}>
                <td className={td}>
                  <div className="font-bold text-slate-900">{profile.code} <span className="text-[10px] text-slate-400">v{profile.version}</span></div>
                  <div className="text-[10px] text-slate-400">{profile.profile_type}</div>
                </td>
                <td className={td}>{profile.country_code} · {profile.vertical}</td>
                <td className={`${td} text-[11px]`}>
                  Seller: {profile.seller_of_record} · Pay: {profile.payment_role}
                  <div className="text-[10px] text-slate-400">Tax: {profile.tax_party} · Invoice: {profile.invoice_issuer}</div>
                </td>
                <td className={td}>{formatDate(profile.effective_from)}<div className="text-[10px] text-slate-400">to {profile.effective_to ? formatDate(profile.effective_to) : "open-ended"}</div></td>
                <td className={td}>
                  <div className="flex flex-col gap-1 items-start">
                    <StatusBadge status={profile.status} />
                    {profile.is_gated && <span className="inline-flex items-center gap-1 text-[10px] font-bold text-rose-700"><ShieldAlert className="w-3 h-3" /> Gated</span>}
                  </div>
                </td>
                <td className={`${td} whitespace-nowrap`}>
                  <div className="flex gap-1.5">
                    <button
                      disabled={!PROFILE_TRANSITIONS[profile.status]?.length}
                      onClick={() => openTransition({
                        title: `Change status — ${profile.code} v${profile.version}`,
                        options: PROFILE_TRANSITIONS[profile.status] || [],
                        mode: "catalogue",
                        submit: (p) => api.commercial.transitionRoleProfile(profile.id, { to_status: p.to_status, reason: p.reason, approval_reference: p.approval_reference }),
                      }, reload)}
                      className="h-7 px-2.5 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
                    >
                      Status
                    </button>
                    <button onClick={() => newVersion(profile)} className="h-7 px-2.5 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-50">
                      New version
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableShell>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Country gates
// ---------------------------------------------------------------------------

function GatePanel({ openTransition }: { openTransition: (req: TransitionRequest, reload: () => void) => void }) {
  const loader = useCallback(() => fetchAllPages<CountryGate>("/commercial/admin/country-gates/"), []);
  const { items, loading, error, reload } = useLoader(loader);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ country_code: "", vertical: "SERVICES", capability: "DISCOVERY", currencies: "", tax_schedule_reference: "", notes: "" });
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [history, setHistory] = useState<CountryGate | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const create = async () => {
    setSaving(true);
    setFormError(null);
    try {
      await api.commercial.createGate({
        country_code: form.country_code,
        vertical: form.vertical,
        capability: form.capability,
        allowed_currencies: form.currencies.split(",").map((c) => c.trim()).filter(Boolean),
        tax_schedule_reference: form.tax_schedule_reference,
        notes: form.notes,
      });
      setShowForm(false);
      reload();
    } catch (err) {
      setFormError(errorText(err));
    } finally {
      setSaving(false);
    }
  };

  const openHistory = async (gate: CountryGate) => {
    setHistoryError(null);
    try {
      setHistory(await api.commercial.getGate(gate.id));
    } catch (err) {
      setHistoryError(errorText(err));
    }
  };

  return (
    <div className="space-y-3">
      <PanelHeader
        title="Country / market gates"
        subtitle="Every gate starts CLOSED. Activation moves one evidenced step at a time; a missing gate is closed (§9, §22)."
        onCreate={() => setShowForm((v) => !v)}
        createLabel="New gate"
        onReload={reload}
      />
      {showForm && (
        <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 grid grid-cols-1 md:grid-cols-3 gap-3">
          <Field label="Country (ISO-2)"><input value={form.country_code} onChange={(e) => set("country_code")(e.target.value.toUpperCase())} maxLength={2} className={inputClass} /></Field>
          <Field label="Vertical"><Select value={form.vertical} onChange={set("vertical")} options={VERTICALS} /></Field>
          <Field label="Capability"><Select value={form.capability} onChange={set("capability")} options={CAPABILITIES} /></Field>
          <Field label="Allowed currencies" hint="Comma-separated ISO 4217 codes"><input value={form.currencies} onChange={(e) => set("currencies")(e.target.value.toUpperCase())} className={inputClass} /></Field>
          <Field label="Tax schedule reference" hint="Required before the gate can be enabled"><input value={form.tax_schedule_reference} onChange={(e) => set("tax_schedule_reference")(e.target.value)} className={inputClass} /></Field>
          <Field label="Notes"><input value={form.notes} onChange={(e) => set("notes")(e.target.value)} className={inputClass} /></Field>
          <div className="md:col-span-3 flex items-center justify-between gap-3">
            <ErrorBanner message={formError} />
            <button onClick={create} disabled={saving} className="h-9 px-4 rounded-lg bg-slate-950 text-white text-xs font-bold disabled:opacity-50 ml-auto">
              {saving ? "Creating…" : "Create closed gate"}
            </button>
          </div>
        </div>
      )}
      <ErrorBanner message={error || historyError} onRetry={error ? reload : undefined} />
      <TableShell loading={loading} empty={!items.length}>
        <table className="w-full">
          <thead>
            <tr>
              <th className={th}>Market</th><th className={th}>Capability</th><th className={th}>State</th>
              <th className={th}>Currencies</th><th className={th}>Tax schedule</th><th className={th}></th>
            </tr>
          </thead>
          <tbody>
            {items.map((gate) => (
              <tr key={gate.id}>
                <td className={td}><div className="font-bold text-slate-900">{gate.country_code}</div><div className="text-[10px] text-slate-400">{gate.vertical}</div></td>
                <td className={td}>{gate.capability}{gate.is_regulated && <div className="text-[10px] font-bold text-rose-700">Regulated — locked in R1</div>}</td>
                <td className={td}>
                  <div className="flex items-center gap-1.5">
                    {gate.is_open ? <Unlock className="w-3.5 h-3.5 text-emerald-600" /> : <Lock className="w-3.5 h-3.5 text-slate-400" />}
                    <StatusBadge status={gate.status} />
                  </div>
                  <div className="text-[10px] text-slate-400 mt-0.5">activation v{gate.version}</div>
                </td>
                <td className={td}>{gate.allowed_currencies.length ? gate.allowed_currencies.join(", ") : "—"}</td>
                <td className={`${td} max-w-[180px] text-slate-500`}>{gate.tax_schedule_reference || "—"}</td>
                <td className={`${td} whitespace-nowrap`}>
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => openTransition({
                        title: `Transition gate — ${gate.country_code}/${gate.vertical}/${gate.capability}`,
                        options: gate.allowed_next_statuses,
                        mode: "gate",
                        submit: (p) => api.commercial.transitionGate(gate.id, { to_status: p.to_status, reason: p.reason, evidence_reference: p.evidence_reference }),
                      }, reload)}
                      className="h-7 px-2.5 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-50"
                    >
                      Transition
                    </button>
                    <button onClick={() => openHistory(gate)} className="h-7 px-2.5 rounded-lg border border-slate-200 text-[11px] font-bold text-slate-700 hover:bg-slate-50 flex items-center gap-1">
                      <History className="w-3 h-3" /> History
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableShell>

      {history && (
        <div className="fixed inset-0 z-50 bg-black/60 flex justify-end" onClick={() => setHistory(null)}>
          <div className="bg-white w-full max-w-md h-full p-5 overflow-y-auto space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-black text-slate-950">{history.country_code}/{history.vertical}/{history.capability}</h4>
              <button onClick={() => setHistory(null)} className="text-slate-400 hover:text-slate-600" aria-label="Close"><X className="w-4 h-4" /></button>
            </div>
            <p className="text-xs text-slate-500">Append-only activation history (newest first).</p>
            {!history.transitions?.length && <p className="text-xs text-slate-500">No transitions yet — the gate is still DESIGNED (closed).</p>}
            {history.transitions?.map((t) => (
              <div key={t.id} className="p-3 rounded-xl border border-slate-200 text-xs space-y-1">
                <div className="flex items-center gap-1.5"><StatusBadge status={t.from_status} /> → <StatusBadge status={t.to_status} /> <span className="text-[10px] text-slate-400 ml-auto">v{t.version_after}</span></div>
                <div className="text-slate-700">{t.reason}</div>
                {t.evidence_reference && <div className="text-[10px] text-slate-500">Evidence: {t.evidence_reference}</div>}
                <div className="text-[10px] text-slate-400">{t.actor_email} · {formatDate(t.created_at)}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Non-binding quote preview
// ---------------------------------------------------------------------------

function PreviewPanel() {
  const [form, setForm] = useState({
    country_code: "", vertical: "VEHICLES", currency: "USD", customer_role: "DEALER", role_profile_code: "",
    sku_code: "", payer_role: "DEALER", quantity: "1", plan_code: "", face_value: "", discount: "", delivery: "", tax: "",
    tax_determination_reference: "",
  });
  const [result, setResult] = useState<CommercialQuotePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const set = (key: keyof typeof form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));
  const exponent = currencyExponent(form.currency);

  const run = async () => {
    setError(null);
    setResult(null);
    let amounts: Record<string, number>;
    try {
      amounts = {
        face_value_minor: parseMajorToMinor(form.face_value, exponent) ?? 0,
        discount_minor: parseMajorToMinor(form.discount, exponent) ?? 0,
        delivery_minor: parseMajorToMinor(form.delivery, exponent) ?? 0,
        tax_minor: parseMajorToMinor(form.tax, exponent) ?? 0,
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Invalid amount.");
      return;
    }
    setRunning(true);
    try {
      setResult(await api.commercial.previewQuote({
        country_code: form.country_code,
        vertical: form.vertical,
        currency: form.currency,
        customer_role: form.customer_role,
        role_profile_code: form.role_profile_code,
        fee_items: [{ sku_code: form.sku_code, payer_role: form.payer_role, quantity: Number(form.quantity) || 1, plan_code: form.plan_code }],
        tax_determination_reference: form.tax_determination_reference,
        ...amounts,
      }));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-black text-slate-950">Quote preview (non-binding)</h3>
        <p className="text-xs text-slate-500 mt-0.5">
          Runs the quote engine over draft/illustrative data and lists every control that would block a binding quote.
          Nothing is saved and nothing shown here is a price offer.
        </p>
      </div>
      <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 grid grid-cols-1 md:grid-cols-4 gap-3">
        <Field label="Country (ISO-2)"><input value={form.country_code} onChange={(e) => set("country_code")(e.target.value.toUpperCase())} maxLength={2} className={inputClass} /></Field>
        <Field label="Vertical"><Select value={form.vertical} onChange={set("vertical")} options={VERTICALS} /></Field>
        <Field label="Currency"><Select value={form.currency} onChange={set("currency")} options={CURRENCIES} /></Field>
        <Field label="Customer role"><Select value={form.customer_role} onChange={set("customer_role")} options={PAYER_ROLES} /></Field>
        <Field label="Role profile code"><input value={form.role_profile_code} onChange={(e) => set("role_profile_code")(e.target.value.toUpperCase())} className={inputClass} /></Field>
        <Field label="SKU code"><input value={form.sku_code} onChange={(e) => set("sku_code")(e.target.value.toUpperCase())} className={inputClass} /></Field>
        <Field label="Fee payer role"><Select value={form.payer_role} onChange={set("payer_role")} options={PAYER_ROLES} /></Field>
        <Field label="Quantity"><input value={form.quantity} onChange={(e) => set("quantity")(e.target.value.replace(/\D/g, ""))} className={inputClass} /></Field>
        <Field label="Plan code (optional)"><input value={form.plan_code} onChange={(e) => set("plan_code")(e.target.value.toUpperCase())} className={inputClass} /></Field>
        <Field label={`Goods/service value (${form.currency})`}><input value={form.face_value} onChange={(e) => set("face_value")(e.target.value)} className={inputClass} /></Field>
        <Field label="Discount"><input value={form.discount} onChange={(e) => set("discount")(e.target.value)} className={inputClass} /></Field>
        <Field label="Delivery"><input value={form.delivery} onChange={(e) => set("delivery")(e.target.value)} className={inputClass} /></Field>
        <Field label="Tax"><input value={form.tax} onChange={(e) => set("tax")(e.target.value)} className={inputClass} /></Field>
        <Field label="Tax determination ref."><input value={form.tax_determination_reference} onChange={(e) => set("tax_determination_reference")(e.target.value)} className={inputClass} /></Field>
        <div className="md:col-span-2 flex items-end justify-end">
          <button onClick={run} disabled={running} className="h-9 px-4 rounded-lg bg-slate-950 text-white text-xs font-bold disabled:opacity-50 flex items-center gap-1">
            <Calculator className="w-3.5 h-3.5" /> {running ? "Calculating…" : "Run preview"}
          </button>
        </div>
      </div>
      <ErrorBanner message={error} />
      {result && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2 py-0.5 rounded-md border border-amber-300 bg-amber-50 text-[10px] font-black text-amber-900">NON-BINDING PREVIEW</span>
            {result.would_be_binding
              ? <span className="text-xs font-bold text-emerald-700">All controls pass — a binding quote could be issued.</span>
              : <span className="text-xs font-bold text-rose-700">{result.blocking_reasons.length} control(s) would block a binding quote.</span>}
          </div>
          {result.blocking_reasons.length > 0 && (
            <ul className="space-y-1">
              {result.blocking_reasons.map((reason, index) => (
                <li key={`${reason.rule}-${index}`} className="text-xs text-rose-800 bg-rose-50 border border-rose-200 rounded-lg px-3 py-1.5">
                  <span className="font-black">{reason.rule}</span> — {reason.message}
                </li>
              ))}
            </ul>
          )}
          <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
            <table className="w-full">
              <thead><tr><th className={th}>Line</th><th className={th}>Payer</th><th className={th}>Customer payable</th><th className={`${th} text-right`}>Amount</th></tr></thead>
              <tbody>
                {result.lines.map((line, index) => (
                  <tr key={index}>
                    <td className={td}>{line.description}{line.rate_status && <div className="text-[10px] text-slate-400">SKU {line.sku_status} · rate {line.rate_status}</div>}</td>
                    <td className={td}>{line.payer_role || "—"}</td>
                    <td className={td}>{line.is_customer_payable ? "Yes" : "No (other party)"}</td>
                    <td className={`${td} text-right font-bold`}>{formatMinor(line.amount_minor, result.currency, result.currency_exponent)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="p-3 rounded-xl border border-slate-200 bg-white"><div className="text-slate-500">Commissionable base</div><div className="font-black text-slate-950">{formatMinor(result.commissionable_base_minor, result.currency, result.currency_exponent)}</div></div>
            <div className="p-3 rounded-xl border border-slate-200 bg-white"><div className="text-slate-500">Platform fee</div><div className="font-black text-slate-950">{formatMinor(result.platform_fee_minor, result.currency, result.currency_exponent)}</div></div>
            <div className="p-3 rounded-xl border border-slate-200 bg-white"><div className="text-slate-500">Customer total</div><div className="font-black text-slate-950">{formatMinor(result.customer_total_minor, result.currency, result.currency_exponent)}</div></div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Quotes & outbox (read-only)
// ---------------------------------------------------------------------------

function QuotesPanel() {
  const loader = useCallback(async () => (await api.commercial.listAdminQuotes()).results, []);
  const { items, loading, error, reload } = useLoader<CommercialQuote>(loader);
  return (
    <div className="space-y-3">
      <PanelHeader title="Issued quotes" subtitle="Immutable quote snapshots (latest 20). Accepted terms never change after rate or plan updates." onReload={reload} />
      <ErrorBanner message={error} onRetry={reload} />
      <TableShell loading={loading} empty={!items.length}>
        <table className="w-full">
          <thead><tr><th className={th}>Quote</th><th className={th}>Customer</th><th className={th}>Market</th><th className={`${th} text-right`}>Total</th><th className={th}>Status</th><th className={th}>Terms hash</th></tr></thead>
          <tbody>
            {items.map((quote) => (
              <tr key={quote.id}>
                <td className={td}><div className="font-bold text-slate-900">{quote.quote_number}</div><div className="text-[10px] text-slate-400">{formatDate(quote.created_at)}</div></td>
                <td className={td}>{quote.customer_email}<div className="text-[10px] text-slate-400">{quote.customer_role}</div></td>
                <td className={td}>{quote.country_code} · {quote.vertical}<div className="text-[10px] text-slate-400">gate v{quote.gate_version}</div></td>
                <td className={`${td} text-right font-bold`}>{formatMinor(quote.customer_total_minor, quote.currency, quote.currency_exponent)}</td>
                <td className={td}><StatusBadge status={quote.effective_status} /></td>
                <td className={`${td} font-mono text-[10px] text-slate-500`}>{quote.terms_hash.slice(0, 16)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableShell>
    </div>
  );
}

function OutboxPanel() {
  const [topic, setTopic] = useState("");
  const loader = useCallback(async () => (await api.commercial.listOutbox(topic ? { topic } : undefined)).results, [topic]);
  const { items, loading, error, reload } = useLoader<OutboxEventRecord>(loader);
  return (
    <div className="space-y-3">
      <PanelHeader title="Event outbox" subtitle="Versioned events written in the same transaction as each change (latest 20). Published by the publish_outbox_events command." onReload={reload} />
      <div className="flex items-center gap-2 text-xs">
        <span className="font-bold text-slate-500">Topic</span>
        <input value={topic} onChange={(e) => setTopic(e.target.value.trim())} placeholder="e.g. quote.accepted" className={inputClass} />
      </div>
      <ErrorBanner message={error} onRetry={reload} />
      <TableShell loading={loading} empty={!items.length}>
        <table className="w-full">
          <thead><tr><th className={th}>Topic</th><th className={th}>Aggregate</th><th className={th}>Occurred</th><th className={th}>Delivery</th><th className={th}>Payload</th></tr></thead>
          <tbody>
            {items.map((event) => (
              <tr key={event.id}>
                <td className={td}><div className="font-bold text-slate-900">{event.topic}</div><div className="text-[10px] text-slate-400">schema v{event.schema_version}</div></td>
                <td className={td}>{event.aggregate_type}<div className="text-[10px] text-slate-400 font-mono">{event.aggregate_id.slice(0, 8)}…</div></td>
                <td className={td}>{formatDate(event.occurred_at)}</td>
                <td className={td}><StatusBadge status={event.status} />{event.last_error && <div className="text-[10px] text-rose-700 mt-0.5">{event.last_error}</div>}</td>
                <td className={`${td} font-mono text-[10px] text-slate-500 max-w-[280px] break-all`}>{JSON.stringify(event.payload)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TableShell>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shell
// ---------------------------------------------------------------------------

const PANELS: Array<{ id: PanelId; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { id: "skus", label: "SKU Catalogue", icon: Tags },
  { id: "rates", label: "Rate Schedules", icon: Percent },
  { id: "profiles", label: "Role Profiles", icon: Users },
  { id: "gates", label: "Country Gates", icon: Globe2 },
  { id: "preview", label: "Quote Preview", icon: Calculator },
  { id: "quotes", label: "Quotes", icon: FileText },
  { id: "outbox", label: "Event Outbox", icon: Radio },
];

export default function CommercialAdminView() {
  const [panel, setPanel] = useState<PanelId>("skus");
  const [transition, setTransition] = useState<{ request: TransitionRequest; reload: () => void } | null>(null);

  const openTransition = useCallback((request: TransitionRequest, reload: () => void) => {
    setTransition({ request, reload });
  }, []);

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-slate-950 text-amber-400 flex items-center justify-center shrink-0">
          <Landmark className="w-5 h-5" />
        </div>
        <div>
          <h2 className="text-lg font-black text-slate-950">Commercial Control Plane</h2>
          <p className="text-xs text-slate-500">SKU catalogue, market gates, legal role profiles, effective-dated rates and immutable quotes (R1).</p>
        </div>
      </div>

      <div className="p-3 rounded-xl border border-amber-200 bg-amber-50 text-xs text-amber-900 flex items-start gap-2">
        <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5" />
        <span>
          Safety posture: SKUs start <b>DRAFT</b>, gates start <b>CLOSED</b>, illustrative bands are never prices, and regulated
          finance/insurance products cannot be approved or enabled. Approvals require a second person and an approval reference.
          No payments, payouts or settlement happen here.
        </span>
      </div>

      <div className="flex flex-wrap gap-1.5 border-b border-slate-200 pb-2">
        {PANELS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setPanel(id)}
            className={`h-8 px-3 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors ${
              panel === id ? "bg-slate-950 text-white" : "text-slate-600 hover:bg-slate-100"
            }`}
          >
            <Icon className="w-3.5 h-3.5" /> {label}
          </button>
        ))}
      </div>

      {panel === "skus" && <SkuPanel openTransition={openTransition} />}
      {panel === "rates" && <RatePanel openTransition={openTransition} />}
      {panel === "profiles" && <RoleProfilePanel openTransition={openTransition} />}
      {panel === "gates" && <GatePanel openTransition={openTransition} />}
      {panel === "preview" && <PreviewPanel />}
      {panel === "quotes" && <QuotesPanel />}
      {panel === "outbox" && <OutboxPanel />}

      {transition && (
        <TransitionDialog
          request={transition.request}
          onClose={() => setTransition(null)}
          onDone={() => {
            const reload = transition.reload;
            setTransition(null);
            reload();
          }}
        />
      )}
    </div>
  );
}
