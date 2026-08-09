import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Search } from "lucide-react";

import { AppLayout } from "@/layouts/AppLayout";
import { Card } from "@/components/astitva/Card";
import { Badge } from "@/components/astitva/Badge";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/astitva/States";
import { agentApi } from "@/api/client";

interface SchemeCard {
  name?: string;
  scheme_name?: string;
  category?: string;
  state?: string;
  description?: string;
  benefits?: string[];
  eligibility_reasoning?: string;
  target_group?: string;
  source?: string;
}

interface GovernmentData {
  answer: string;
  recommended_schemes: SchemeCard[];
  additional_context: string;
  sources: string[];
}

const categories = ["all", "Housing", "Healthcare", "Finance", "Employment", "Education", "Legal"] as const;

export default function OpportunitiesPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<GovernmentData | null>(null);
  const [error, setError] = useState("");
  const [searched, setSearched] = useState(false);

  const search = async (q: string, cat: string) => {
    if (!q.trim() && cat === "all") return;
    setLoading(true);
    setError("");
    try {
      const payload: Parameters<typeof agentApi.government>[0] = { query: q || "support available for me" };
      if (cat !== "all") payload.category = cat;
      const resp = await agentApi.government(payload);
      setData(resp as unknown as GovernmentData);
      setSearched(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  };

  // Auto-load on mount with a broad query
  useEffect(() => {
    void search("support available for women", "all");
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const schemes = data?.recommended_schemes ?? [];
  const filtered = schemes.filter((s) => {
    const name = s.name ?? s.scheme_name ?? "";
    const matchQuery =
      !query.trim() ||
      name.toLowerCase().includes(query.toLowerCase()) ||
      (s.description ?? "").toLowerCase().includes(query.toLowerCase());
    const matchCat = category === "all" || (s.category ?? "").toLowerCase() === category.toLowerCase();
    return matchQuery && matchCat;
  });

  return (
    <AppLayout title="Opportunities" subtitle="Government schemes and support matched to your situation.">
      <div className="space-y-6">
        {/* Search bar */}
        <form
          className="flex gap-2"
          onSubmit={(e) => { e.preventDefault(); void search(query, category); }}
        >
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-4 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search schemes, legal aid, housing, employment…"
              className="min-h-12 w-full rounded-full border border-input bg-surface pr-4 pl-11 text-sm text-foreground placeholder:text-muted-foreground"
            />
          </div>
          <Button type="submit" loading={loading}>Search</Button>
        </form>

        {/* Category filter */}
        <div className="flex flex-wrap gap-2">
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              aria-pressed={category === cat}
              onClick={() => { setCategory(cat); void search(query || "support", cat); }}
              className={`min-h-9 rounded-full border px-3.5 text-xs font-medium capitalize transition-colors ${
                category === cat
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border bg-surface text-muted-foreground hover:text-foreground"
              }`}
            >
              {cat === "all" ? "All categories" : cat}
            </button>
          ))}
        </div>

        {error ? (
          <p className="rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{error}</p>
        ) : null}

        {loading ? (
          <LoadingState message="Searching government schemes database…" />
        ) : searched ? (
          <>
            <p className="text-sm text-muted-foreground" aria-live="polite">
              {filtered.length} scheme{filtered.length !== 1 ? "s" : ""} found
            </p>

            {/* AI answer */}
            {data?.answer && data.answer !== "LLM provider placeholder response." ? (
              <Card>
                <p className="text-xs font-semibold tracking-wide text-primary uppercase mb-2">
                  AI Analysis
                </p>
                <p className="text-sm leading-relaxed text-muted-foreground whitespace-pre-wrap">
                  {data.answer}
                </p>
              </Card>
            ) : null}

            {/* Schemes grid */}
            {filtered.length > 0 ? (
              <div className="grid gap-4 md:grid-cols-2">
                {filtered.map((scheme, i) => (
                  <SchemeCard key={i} scheme={scheme} />
                ))}
              </div>
            ) : (
              <div className="rounded-2xl border border-dashed border-border bg-surface px-6 py-14 text-center">
                <p className="font-semibold text-foreground">No schemes match your filters</p>
                <p className="mt-1 text-sm text-muted-foreground">
                  Try a different search term or use the AI Guide for personalized advice.
                </p>
                <Button className="mt-4" variant="outline" asChild>
                  <Link to="/chat">Ask AI Guide</Link>
                </Button>
              </div>
            )}

            {data?.sources && data.sources.length > 0 ? (
              <p className="text-xs text-muted-foreground">
                Sources: {data.sources.join(", ")}
              </p>
            ) : null}
          </>
        ) : null}
      </div>
    </AppLayout>
  );
}

function SchemeCard({ scheme }: { scheme: SchemeCard }) {
  const name = scheme.name ?? scheme.scheme_name ?? "Unnamed scheme";
  return (
    <article className="flex flex-col rounded-2xl border border-border bg-surface p-5 transition-shadow hover:shadow-[0_14px_34px_-26px_rgba(43,23,36,0.6)]">
      <div>
        <h3 className="text-base font-semibold text-foreground">{name}</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {scheme.category ? <Badge tone="sand">{scheme.category}</Badge> : null}
          {scheme.state ? <Badge tone="sage">{scheme.state}</Badge> : null}
        </div>
      </div>

      {scheme.description ? (
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground line-clamp-3">
          {scheme.description}
        </p>
      ) : null}

      {scheme.eligibility_reasoning ? (
        <div className="mt-3 rounded-xl bg-secondary-soft/70 p-3 text-sm">
          <p className="font-medium text-foreground">Why this matches you</p>
          <p className="mt-1 text-muted-foreground">{scheme.eligibility_reasoning}</p>
        </div>
      ) : null}

      {scheme.benefits && scheme.benefits.length > 0 ? (
        <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
          {scheme.benefits.slice(0, 3).map((b, i) => <li key={i}>• {b}</li>)}
        </ul>
      ) : null}

      <div className="mt-4 pt-2">
        <Button size="sm" variant="outline" asChild>
          <Link to="/chat">Learn more via Guide</Link>
        </Button>
      </div>
    </article>
  );
}
