import type { Metadata } from "next";
import Link from "next/link";

import SiteFooter from "../../_components/SiteFooter";
import SiteHeader from "../../_components/SiteHeader";
import { POSTS, blogPostingJsonLd } from "../_lib/posts";

export const metadata: Metadata = {
  alternates: { canonical: "/blog/state-of-the-art-beam-10m" },
  title: "Stash: State of the Art on the BEAM 10M Benchmark · Stash",
  description:
    "Stash sets state of the art on BEAM at every scale, by +4.6 points at 10M tokens, where the grep baseline collapses. What curation costs, why cost per question grows far slower than the corpus, and why that beats putting everything in context.",
};

const STALE_PAPER = "https://arxiv.org/abs/2605.06527";

export default function StateOfTheArtBeam10mPage() {
  const post = POSTS["state-of-the-art-beam-10m"];
  const authors = [post.author, ...(post.coauthors ?? [])].map((a) => a.name);

  return (
    <main className="min-h-screen bg-background text-foreground">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(blogPostingJsonLd(post)) }}
      />
      <SiteHeader current="Blog" />

      <article className="mx-auto max-w-[720px] px-7 pb-24 pt-16">
        <h1 className="text-balance font-display text-[clamp(32px,4.4vw,52px)] font-medium leading-[1.06] tracking-[-0.03em] text-ink">
          Stash: State of the Art on the BEAM 10M Benchmark
        </h1>
        <p className="mt-5 text-[14px] text-muted">
          By {authors.join(" and ")} ·{" "}
          <time dateTime={post.datePublished}>{post.byline}</time>
        </p>

        <div className="prose prose-lg mt-10">
          <Figure
            src="/blog/beam-10m-sota.webp"
            width={1258}
            height={832}
            alt="Bar chart of BEAM-10M scores: Stash 0.726, Exabase M-1 0.680, Hindsight 0.641, Honcho 0.406, and a grep baseline 0.528. Stash is 4.6 points over the previous state of the art."
            caption="Figure 1 — Stash sets state of the art at BEAM-10M, the largest scale the benchmark evaluates. Stash 0.7256, Exabase M-1 0.680, Hindsight 0.641, Honcho 0.406, grep baseline 0.528."
          />

          <h2>Introduction</h2>
          <p>
            How do we make agents handle corpora effectively once they exceed their context
            window?
          </p>
          <p>
            Historically (in ~2023!), the solution to this is known as RAG (Retrieval-Augmented
            Generation), which uses vector search to inject semantically relevant information into
            the context window at inference time. Since then, the space of techniques has expanded
            to include knowledge graphs, leveraging databases, and building LLM wikis. The emerging
            consensus as of this writing is to use a series of markdown files stored in a virtual
            file system that an agent can grep over. While this is highly effective for smaller
            corpus sizes, it scales extremely poorly in both accuracy and token spend, and can be
            prone to confabulation and catastrophic forgetting. This is because, when given only a
            filesystem, agents have great difficulty proving that some semantic element is{" "}
            <em>not</em> present within that filesystem. This is very relevant to both benchmarks
            and real-world use, as there are many situations where we may have one transcript with
            an outdated answer to a question, which has then been superseded by a newer transcript
            with fresh changes. When armed with nothing more than a filesystem, a model cannot be
            confident that it has the most up-to-date, accurate version of any piece of information
            unless it reads a lot of transcripts and documents that are ultimately irrelevant.
          </p>
          <p>
            For example, let&rsquo;s assume a corpus contains user growth figures from last week
            and a revised figure based on a new methodology. Under existing retrieval-based memory
            approaches, the agent can&rsquo;t tell which figures are up-to-date without reading the
            surrounding context of each. It also can&rsquo;t tell whether an even newer version
            exists somewhere its queries didn&rsquo;t find. At 100K tokens this might be reasonable,
            since an agent can traverse the entire corpus easily. At 10M and above, issues like this
            lead to confidently wrong answers. Moreover, memory is as much about forgetting as it is
            about remembering. No matter how good retrieval is, adding more and more information to
            the corpus will deteriorate its performance because the difficulty of a retrieval
            problem scales with its corpus size.
          </p>
          <p>
            We designed Stash to solve these problems. Stash organizes all of your data, from
            important files and internal documents to agent trajectories, into a virtual filesystem
            agents can easily search over. It then automatically reads from that filesystem to
            create an internal wiki for your organization or project. These two insights are
            important: agents are post-trained extensively on navigating file systems, which is why
            our memory system is file-system-shaped. We create and curate a wiki in order to allow
            models to access the important parts of your organization&rsquo;s history and knowledge
            base without having to read or grep through millions of tokens of transcripts every
            session.
          </p>
          <p>
            The core insight behind Stash, which puts it above alternative memory models like simple
            agentic search or knowledge graphs, is that we can use LLMs to usefully turn a
            user&rsquo;s corpus of many disparate transcripts into specific, concrete insights that
            can be delivered cheaply and compactly to your agents. They can then be cheaply updated
            on-demand in a lazy fashion as we add new information into the system. Every retrieval
            operation also becomes an update operation where we decide whether to update the
            existing insights to prevent information from becoming stale. By paying a small upfront
            cost, in the form of model calls that constantly and proactively integrate new
            transcripts into your Stash&rsquo;s knowledge base, we are able to attain consistently
            state-of-the-art performance on benchmarks while dramatically reducing answer time and
            scaling better with number-of-tokens than normal dreaming/sleep-time systems.
          </p>

          <h2>How we think about benchmarks</h2>
          <p>
            The previous generation of memory benchmarks, like LongMemEval-S, LoCoMo, and others,
            contain corpuses of data that are easily able to fit inside modern LLMs&rsquo; context
            windows of ~1M tokens. This makes them very useful for testing models&rsquo; recall
            within their context windows, but ultimately means that they are wildly
            unrepresentative of real-world memory tasks on the scale of projects or organizations.
            Since these datasets can fit into a single context window, they tend to be saturated
            when memory systems test on them: all systems score within a couple percentage points of
            the theoretical maximum. Benchmarks like LongMemEval-S are therefore not useful as
            measures of a memory system&rsquo;s capability because they are not able to distinguish
            between different systems. Instead, they are often measuring benchmaxxing (e.g. prompt
            optimization, model choice, etc.) with some companies reporting scores greater than the
            theoretical maximum.
          </p>
          <p>
            The story of memory in real projects has, broadly, been a story of having more data
            than we know what to do with: individual agent transcripts can often contain more tokens
            than all the context associated with a LoCoMo question combined, and the ideal memory
            system will be able to retrieve data from arbitrarily large collections of input data.
            Thus, we believe that larger benchmarks like BEAM-10M, with corpus sizes of over 10M,
            are better suited to testing modern memory systems. Note that we had a new hire generate
            &gt;10M tokens in his first week, so even 10M tokens fails to capture the true size of
            production systems. Moreover, these are largely still needle-in-the-haystack retrieval
            benchmarks which fail to capture the full requirements for a good memory system, but
            they are a good necessary step on the path to true agentic memory. In addition, we also
            value benchmarks that go beyond retrieval. The <Lnk href={STALE_PAPER}>STALE</Lnk>{" "}
            benchmark tests a problem we internally label blast radius: information is bounded by
            time, scope, or priority. Stash nearly saturates STALE (see our post{" "}
            <Link
              href="/blog/why-memory-is-unsolved"
              className="text-brand underline underline-offset-4 transition hover:text-ink"
            >
              Why Memory Is Unsolved
            </Link>
            ).
          </p>

          <Figure
            src="/blog/beam-corpus-vs-context.webp"
            width={2048}
            height={1206}
            alt="Log-scale bar chart of tokens per test case: LoCoMo 20K, LongMemEval-S 115K, BEAM-100K 153K, BEAM-500K 557K, BEAM-1M 1.15M, LongMemEval-M 1.5M, BEAM-10M 10M. A 200K line marks Haiku 4.5's context window and a 1M line marks Opus 5, Sonnet 5 and Gemini 3 Pro; no context window reaches beyond 1M."
            caption="Figure 2 — LoCoMo and LongMemEval-S fit inside even the small context windows; BEAM does not."
          />

          <h2>Results</h2>
          <h3>BEAM</h3>
          <p>
            BEAM is a benchmark that tests long-term memory in conversational agents at scales far
            too large to fit into any model&rsquo;s context window. Each test case is a single
            simulated agent transcript of 100K to 10M tokens, spanning hundreds of simulated days in
            which facts are stated, revised, and contradicted. Scoring is nugget-based: reference
            answers are decomposed into atomic criteria and an LLM judge scores each at 0, 0.5, or
            1.
          </p>
          <Table
            head={["Split", "Stash", "Exabase M-1", "Hindsight", "Honcho", "grep baseline"]}
            rows={[
              ["100K", "0.8008", "0.769", "0.734", "0.630", "0.720"],
              ["500K", "0.7656", "—", "—", "—", "—"],
              ["1M", "0.7692", "0.750", "0.739", "0.631", "0.657"],
              ["10M", "0.7256", "0.680", "0.641", "0.406", "0.528"],
            ]}
            boldCol={1}
          />
          <p>
            Stash leads at every scale, by +3.2 points at 100K, +1.9 at 1M, and +4.6 at 10M. The
            margin is widest at the largest scale, which is the one that matters — 10M tokens is
            roughly a week of daily agent conversations, or a company&rsquo;s entire internal
            documentation corpus.
          </p>

          <Figure
            src="/blog/beam-score-across-scale.webp"
            width={1289}
            height={900}
            alt="Line chart of BEAM score against corpus size from 100K to 10M tokens. Stash stays on top, falling from 0.80 to 0.73. Exabase M-1 and Hindsight fall to 0.68 and 0.64, Honcho drops to 0.41, and the grep baseline falls from 0.72 to 0.53."
            caption="Figure 3 — Stash leads at every scale, and the grep baseline drops sharply as the corpus grows."
          />

          <Table
            head={["Split", "Stash", "grep", "Abs gain", "% gain"]}
            rows={[
              ["100K", "0.8008", "0.720", "+0.081", "+11.2%"],
              ["1M", "0.7692", "0.657", "+0.112", "+17.1%"],
              ["10M", "0.7256", "0.528", "+0.198", "+37.4%"],
            ]}
          />
          <p>
            The advantage more than triples from 100K to 10M. Almost all of that comes from the
            baseline collapsing rather than from Stash improving: grep gives up 19.2 points across
            the range, Stash gives up 7.5. Curation is a fixed overhead paid against a corpus that
            keeps growing, so the bigger the corpus, the better that trade looks.
          </p>

          <Figure
            src="/blog/beam-gain-over-grep.webp"
            width={1126}
            height={839}
            alt="Bar chart of Stash's relative gain over the grep baseline: +11.2% at 100K (0.801 vs 0.720), +17.1% at 1M (0.769 vs 0.657), and +37.4% at 10M (0.726 vs 0.528)."
            caption="Figure 4 — The advantage over a grep baseline more than triples from 100K to 10M."
          />

          <h3>Token use and cost</h3>
          <p>
            Curation costs roughly $0.18 per million tokens of corpus, and that figure holds across
            a 13x range in corpus size: $0.57 at 100K, $3.57 at 500K, $7.29 at 1M, which works out
            to $0.185, $0.183, and $0.181 per million respectively. The write path therefore scales
            linearly in the size of what it ingests, with no compounding cost as stores grow.
          </p>
          <p>All-in cost, covering curation, answering, and judging:</p>
          <Table
            head={["Split", "Curation", "Answering", "Judging (eval only)", "Total"]}
            rows={[
              ["100K", "$0.57", "$3.41", "$0.60", "$4.58"],
              ["500K", "$3.57", "$9.58", "$1.07", "$14.22"],
              ["1M", "$7.29", "$10.49", "$1.29", "$19.07"],
              ["10M", "$19.91", "$5.27", "$0.40", "$25.58"],
            ]}
          />
          <p>
            There are two ways to look at cost here, and they point in opposite directions. The
            first is cost per million tokens of corpus, which drops about 6x from 100K to 10M. That
            looks great, but it&rsquo;s mostly a side effect of how BEAM is built: every
            conversation gets 20 questions, however long it is. A bigger conversation means the same
            number of questions spread over more tokens, so cost per token falls almost
            automatically. We don&rsquo;t think that number tells you much about Stash.
          </p>
          <p>
            The more useful number is cost per question, which rises from about a cent at 100K to
            about 13 cents at 10M. It does rise, but much more slowly than the data does. From 100K
            to 1M, each conversation gets about 7.5 times bigger, while cost per question only goes
            up about 2.4 times.
          </p>
          <p>
            The reason is that the agent doesn&rsquo;t need to read much more as the corpus grows.
            Going from the 500K split to the 1M split, each conversation roughly doubles in size.
            The context the agent pulls in to answer a question only grows 18% (from about 27,500
            tokens to 32,600), and the cost of answering goes up just 9%. Across the full range,
            conversations grow about 70 times from 100K to 10M, while retrieved context only grows
            about 3 times, from 18,500 tokens to 57,000.
          </p>
          <p>
            The part that does grow with the corpus is curation, the work Stash does once when data
            comes in. Think of it as an upfront cost. For each conversation, curation costs about as
            much as answering 7.5 questions at 500K, or 14 at 1M. After that it never has to be paid
            again, however many questions follow. With BEAM&rsquo;s 20 questions per conversation,
            curation still makes up 27% of the cost at 500K and 41% at 1M, and the more questions
            you ask, the smaller that share gets.
          </p>

          <Figure
            src="/blog/beam-cost-per-question.webp"
            width={1036}
            height={686}
            alt="Log-log chart of cost per question against corpus size per conversation: $0.0115 at 100K, $0.0203 at 500K, $0.0272 at 1M, and a projected $0.1279 at 10M. A dashed line shows where cost would be if it tracked the corpus linearly; at 10M Stash is 6.5x cheaper than linear. A 72x larger corpus costs 11x more per question."
            caption="Figure 5 — Cost per question rises far slower than the corpus. Hollow markers are projected."
          />

          <p>
            An additional question at this point: if the whole corpus fits in a context window, why
            not just put it there? On that view, Stash is only worth it once a project grows past a
            million tokens. Below that, you&rsquo;d skip memory and let the model read everything.
          </p>
          <p>
            Full context does work at that size, but it isn&rsquo;t cheap. We took a 1.15M-token
            conversation from the 1M split and compared the cost of answering its 20 questions both
            ways:
          </p>
          <Table
            head={["Approach", "Per question", "Per conversation"]}
            rows={[
              ["K3 full context", "$3.45", "$68.93"],
              ["K3, 90% cache reuse", "$0.50", "$9.99"],
              ["Stash + K3", "$0.075", "$1.50"],
            ]}
            boldRow={2}
          />

          <Figure
            src="/blog/beam-full-context-cost.webp"
            width={814}
            height={497}
            alt="Log-scale bar chart of cost per question on a 1,148,791-token conversation with 20 questions: K3 full context $3.45, K3 with cache reads $0.50, Stash plus K3 $0.075 including one-time curation — 46x cheaper than full context."
            caption="Figure 6 — Cost per question against putting the same conversation in context."
          />

          <p>
            With full context, the model reads the entire conversation for every question, so you
            pay for all of it every time — about $3.45 a question, or $68.93 for all 20. Stash reads
            the conversation once, when it arrives. After that each question pulls in only the
            roughly 32,600 tokens it needs, so the same 20 questions cost $1.50 all in, curation
            included. That is 46 times cheaper. Caching narrows the gap, because the model
            doesn&rsquo;t reprocess the whole prompt every time: with the prefix served from cache at
            a tenth the input price, the 20 questions come to $9.99. But that is close to a best
            case, and production rarely sees it. It assumes all 20 questions arrive in one burst
            inside the cache&rsquo;s lifetime, but prompt caches expire in minutes while memory gets
            queried hours or months apart — so in real use most questions hit a cold cache and end
            up paying the full $3.45. Even on that generous assumption Stash is 6.7 times cheaper,
            and every cold cache just makes the advantage even bigger.
          </p>

          <h3>Methodology</h3>
          <h4>Benchmark and scoring</h4>
          <p>
            We report all 35 conversations at 500K and 1M (700 questions per split), 20
            conversations at 100K (400 questions), and 10 at 10M (200 questions) included in BEAM.
          </p>
          <p>
            Scoring follows BEAM&rsquo;s official nugget-judge protocol. Each reference answer is
            decomposed into atomic rubric nuggets, and the judge scores the response 0, 0.5, or 1
            against each nugget using the benchmark&rsquo;s own unified judge prompt; a
            question&rsquo;s score is the mean over its nuggets. Event-ordering questions
            additionally receive the paper&rsquo;s ordering metric — the response&rsquo;s lines are
            aligned to the rubric events, then scored as normalized Kendall tau-b × F1, with that
            product taken as the question&rsquo;s score.
          </p>
          <h4>Answering and curation</h4>
          <p>
            We curate and answer questions with Kimi K3 rather than a frontier model. To make sure
            that choice wasn&rsquo;t costing us accuracy, we ran Sonnet 4.6 on the exact same stores
            and compared the two.
          </p>
          <p>
            They came out about even. At 500K, K3 scored 0.7656 to Sonnet&rsquo;s 0.7441 and did
            better on 20 of the 35 conversations. At 1M the scores were nearly identical, 0.7692 to
            0.7661, with K3 ahead on 17 of 35. (Paired differences: +0.0217 at 500K, sd 0.068, t =
            1.87; +0.0023 at 1M, t = 0.32.)
          </p>
          <p>
            With only 35 conversations, neither gap is statistically significant, so we&rsquo;re
            not claiming K3 is the better model. The takeaway is simpler: a model that costs way more
            to run gets you nothing measurable here.
          </p>
          <h4>Judge</h4>
          <p>
            All scores are produced by google/gemini-3-flash-preview. This follows Exabase&rsquo;s
            published protocol, so that answering and judging traverse the same provider path and
            our results sit against theirs on comparable terms rather than being scored by a more or
            less lenient grader.
          </p>

          <h2>Conclusion</h2>
          <p>
            Stash achieves state-of-the-art performance on key memory benchmarks, with the greatest
            gains on the largest benchmarks that are closest to real-life use, such as BEAM-10M,
            where we improve on the state of the art by 4.6 points. Stash also nearly saturates the
            STALE benchmark. This shows that Stash&rsquo;s internal agent wiki enables it to scale well to
            large projects with months of dense, changing history. Stash is able to turn those
            transcripts into consistent insights about a project&rsquo;s state, enabling it to go
            beyond being a glorified context window extension, instead becoming a memory system that
            scales as your projects do.
          </p>
          <p>
            Moving beyond the current state of the art, we&rsquo;re excited to continue working on
            expanding Stash and making it more performant on the largest-context tasks, from large
            repos to whole companies.
          </p>

          <h3>Appendix: scores by ability</h3>
          <Table
            head={["Ability", "500K", "1M"]}
            rows={[
              ["preference_following", "0.951", "0.885"],
              ["contradiction_resolution", "0.905", "0.889"],
              ["information_extraction", "0.890", "0.847"],
              ["knowledge_update", "0.868", "0.804"],
              ["instruction_following", "0.848", "0.879"],
              ["abstention", "0.736", "0.821"],
              ["temporal_reasoning", "0.738", "0.723"],
              ["summarization", "0.719", "0.702"],
              ["multi_session_reasoning", "0.711", "0.718"],
              ["event_ordering", "0.291", "0.425"],
            ]}
          />

          <h3>References</h3>
          <ol>
            <li>
              Tavakoli et al. (2025). &ldquo;Beyond a Million Tokens: Benchmarking and Enhancing
              Long-Term Memory in LLMs.&rdquo; ICLR 2026.
            </li>
            <li>
              Wang et al. (2024). &ldquo;LongMemEval: Benchmarking Long-Term Memory in AI
              Assistants.&rdquo;
            </li>
            <li>
              Hsieh, C-P., et al. (2024). &ldquo;RULER: What&rsquo;s the Real Context Size of Your
              Long-Context Language Models?&rdquo; COLM.
            </li>
            <li>
              Liu, N.F., et al. (2024). &ldquo;Lost in the Middle: How Language Models Use Long
              Contexts.&rdquo; TACL.
            </li>
            <li>
              Modarressi, A., et al. (2025). &ldquo;NoLiMa: Long-Context Evaluation Beyond Literal
              Matching.&rdquo; ICML.
            </li>
            <li>
              Hong, K., Troynikov, A., and Huber, J. (2025). &ldquo;Context Rot: How Increasing
              Input Tokens Impacts LLM Performance.&rdquo; Chroma.
            </li>
          </ol>
        </div>
      </article>

      <SiteFooter />
    </main>
  );
}

function Figure({
  src,
  width,
  height,
  alt,
  caption,
}: {
  src: string;
  width: number;
  height: number;
  alt: string;
  caption: string;
}) {
  return (
    <>
      <img
        src={src}
        width={width}
        height={height}
        loading="lazy"
        alt={alt}
        className="mx-auto w-full rounded-xl border border-border-subtle"
      />
      <p className="text-[14px] italic text-muted">{caption}</p>
    </>
  );
}

// Wide tables scroll inside their own box so the page never scrolls sideways on
// a phone.
function Table({
  head,
  rows,
  boldCol,
  boldRow,
}: {
  head: string[];
  rows: string[][];
  boldCol?: number;
  boldRow?: number;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="tabular-nums">
        <thead>
          <tr>
            {head.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => (
            <tr key={row[0]}>
              {row.map((cell, c) =>
                c === boldCol || r === boldRow ? (
                  <td key={c}>
                    <strong>{cell}</strong>
                  </td>
                ) : (
                  <td key={c}>{cell}</td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Lnk({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-brand underline underline-offset-4 transition hover:text-ink"
    >
      {children}
    </a>
  );
}
