import {
  safeSourceUrl,
  type Candidate,
  type DataMode,
  type Movie,
  type Recommendation,
} from "./domain";

export type Evidence = Recommendation["evidence"][number];
export type ComparedMovie = Movie & {
  snapshot?: {
    candidate: Candidate;
    evidence: Evidence[];
    dataMode: DataMode;
    traceId: string;
  };
};

export const reasonLabels: Record<Candidate["reason"]["kind"], string> = {
  metadata_fact: "影片资料",
  source_opinion: "来源观点",
  matching_inference: "匹配推断",
};

export function evidenceForMovie(
  movie: Movie,
  evidence: Evidence[],
): Evidence[] {
  return evidence.filter((e) => e.movie_id === movie.movie_id);
}

export function sourceSites(evidence: Evidence[]): string[] {
  return [
    ...new Set(
      evidence.flatMap((e) => {
        const url = safeSourceUrl(e.url);
        return url
          ? [new URL(url).hostname.toLowerCase().replace(/^www\./, "")]
          : [];
      }),
    ),
  ];
}

export function snapshotForComparison(
  movie: Movie,
  result?: Recommendation,
): ComparedMovie {
  const candidate = result?.candidates.find(
    (c) => c.movie.movie_id === movie.movie_id,
  );
  return structuredClone({
    ...movie,
    ...(candidate && result
      ? {
          snapshot: {
            candidate,
            evidence: evidenceForMovie(movie, result.evidence),
            dataMode: result.data_mode,
            traceId: result.trace_id,
          },
        }
      : {}),
  });
}
