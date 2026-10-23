# Delta for Knowledge Norms Kernel

## MODIFIED Requirements

### Requirement: buscar and leer

`buscar` MUST take an explicit mode. The no-GPU arm MUST NOT require a reranker. `bm25_ce` MUST still refuse without a real reranker (`RerankerRequerido` unchanged). `leer` MUST return the byte-exact unit and its provenance, including `clasificacion`, for a key at the active SHA, and MUST refuse an unknown key.

In mode `bm25_sin_ce`, once the BM25 top-k exists, `buscar` MUST compose the returned page as follows:

1. Walk the BM25 page from rank 1 to rank k. Within each unit, take article-number citations in textual order from its indexed text.
2. Keep a target only if it resolves to a unit of the SAME statute in the active snapshot. Resolution is against the snapshot, not the BM25 pool: a unit at BM25 rank 54 is eligible.
3. Drop a target that does not resolve, belongs to another statute, is already on the BM25 page, or was already selected as a follow.
4. One hop only: citations inside a followed unit MUST NOT be read.
5. The page size MUST remain k = 10. A follow cited from 0-based page position `p` is admitted only while `len(follows)+1 <= k-1-p`. A follow MUST NOT displace its citing unit or any unit ranked above that citer. Positions only increase, so the first overflow ends selection and later citations are not considered. Admitted follows replace the lowest BM25 ranks and fill the tail in selection order (citing unit's page order, then textual order). A deduped target MUST NOT consume a slot.

Followed units MUST carry no invented score, and the prefix MUST NOT be reordered by any followed-unit score. Rank display is unchanged: `citation_key` order with `orden_presentado` false until the bar is superada for the active SHA. Follow changes the membership of the 10, not rank order, and MUST NOT require estado superada. `bm25_ce`, BM25 constants (k1/b), the expansion step, the gold, the corpus and the bar definition MUST remain unchanged.

(Previously: the no-GPU page was the BM25 top-k with no composition step.)

#### Scenario: No-GPU arm runs without a reranker

- GIVEN no reranker and the no-GPU mode
- WHEN `buscar` runs
- THEN it returns units without error

#### Scenario: bm25_ce without reranker is refused

- GIVEN mode `bm25_ce` and no reranker
- WHEN `buscar` runs
- THEN it refuses with the existing reranker-required error

#### Scenario: Unknown key

- GIVEN a key not present at the active SHA
- WHEN `leer` runs
- THEN it refuses as not found and returns no text

#### Scenario: T-5 shape, cited article enters the page

- GIVEN a BM25 page containing `5589#180` and `5589#187`, both citing art. 276, and `5589#276` outside the page (BM25 rank 54)
- WHEN `buscar` runs in `bm25_sin_ce`
- THEN `5589#276` is in the returned 10, in the tail, once
- AND it displaced the lowest BM25 rank

#### Scenario: Cross-statute citation dropped

- GIVEN a 5589 page unit citing an article number that resolves only in Ley 11027
- WHEN `buscar` runs
- THEN no Ley 11027 unit is added to the page

#### Scenario: Second hop not taken

- GIVEN a followed unit whose own text cites another same-statute article not on the page
- WHEN `buscar` runs
- THEN that second-order target is not added

#### Scenario: Target already on page takes no slot

- GIVEN a cited target already in the BM25 page
- WHEN `buscar` runs
- THEN it appears once, keeps its BM25 position, and no tail slot is consumed for it

#### Scenario: Overflow stops and does not displace the citer

- GIVEN k = 10 and a citation from 0-based position `p` that would make `len(follows)+1 > k-1-p`
- WHEN `buscar` runs
- THEN that follow is dropped and no later citation is considered
- AND a citation from the last slot (`p = k-1`) admits nothing
- AND every admitted follow sits in the tail, below its citing unit

#### Scenario: Unresolvable target dropped

- GIVEN a cited article number absent from the citing unit's statute in the snapshot
- WHEN `buscar` runs
- THEN it is dropped and the BM25 page is otherwise unchanged

#### Scenario: Page size stays 10

- GIVEN any query with follows
- WHEN `buscar` runs in `bm25_sin_ce`
- THEN exactly 10 distinct units are returned, never more
- AND the prefix preserves BM25 relative order, with no score on followed units

#### Scenario: Rank display unchanged

- GIVEN the bar is not superada for the active SHA
- WHEN `buscar` returns a page with follows
- THEN units are in `citation_key` order and `orden_presentado` is false

#### Scenario: bm25_ce untouched

- GIVEN mode `bm25_ce` with a real reranker
- WHEN `buscar` runs
- THEN no citation follow is applied and results equal the pre-change behavior

## Non-Requirements

Moving hit@5 from 22/34 to 25/34 is NOT a requirement of this spec. Success is conformance to the contract above, not a green bar; any bar movement requires a separate, authorized measurement.
