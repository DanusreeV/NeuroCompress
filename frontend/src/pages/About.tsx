import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Card, PageHeader } from "../components/ui";

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div className="grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent-cyan to-accent-violet text-xs font-bold text-navy-950">{n}</div>
      <div>
        <div className="font-medium text-slate-100">{title}</div>
        <div className="text-sm text-slate-400">{children}</div>
      </div>
    </div>
  );
}

export default function About() {
  return (
    <>
      <PageHeader title="About & Research" subtitle="How NeuroCompress works, how it relates to the research that inspired it, and what it does not do." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="The algorithm (what is actually implemented)">
          <div className="space-y-4">
            <Step n={1} title="Normalise & split planes">8-bit grayscale or RGB (other modes are converted and flagged). RGB is coded as three planes in the order G, R, B, so R and B can use already-decoded green information.</Step>
            <Step n={2} title="Causal context per sample">Six causal neighbours (W, N, NW, NE, WW, NN) expressed relative to the LOCO-I “MED” prediction, plus — for R and B — local gradients and prediction residuals of the previously coded planes, plus a plane id. 15 integer features in total.</Step>
            <Step n={3} title="Tiny neural network">A fully connected ReLU network (two hidden layers; 16–128 units) outputs a mean offset and a log-scale. Inference uses fixed-point integer arithmetic, so the encoder and decoder compute bit-identical probabilities on any machine.</Step>
            <Step n={4} title="Probability table">Offset and scale are quantised and select a discretised-logistic distribution over the 256 possible residuals from a precomputed 16-bit integer frequency table (checksum-verified against the table used in training).</Step>
            <Step n={5} title="Range coder">A byte-oriented range coder (LZMA-style carry handling) turns the probabilities into the bitstream. Nothing is estimated: the file size is the real coded size.</Step>
            <Step n={6} title="Self-describing container">Header with dimensions, model name and id, SHA-256 of the original pixels, payload, and a CRC-32 over everything. Corrupted files are rejected; a decode that disagrees with the SHA-256 raises an error.</Step>
          </div>
        </Card>

        <div className="space-y-4">
          <Card title="Parallel decoding via a wavefront order">
            <p className="text-sm text-slate-400">
              Samples are coded in order of <span className="font-mono text-accent-cyan">t = x + 2y</span>. Every context neighbour of a sample has a smaller <span className="font-mono">t</span>, so all samples sharing a value of <span className="font-mono">t</span> are independent. The decoder evaluates the neural network for the whole anti-diagonal front as one batch (vectorised NumPy); only the cheap range-decoding step is sequential. This mirrors the idea of parallel pixel-by-pixel decoding described in the paper; the details here are our own design.
            </p>
            <svg viewBox="0 0 240 110" className="mt-3 w-full max-w-sm">
              {Array.from({ length: 6 }).map((_, y) =>
                Array.from({ length: 12 }).map((_, x) => {
                  const t = x + 2 * y;
                  const hue = (t * 17) % 360;
                  return <rect key={`${x}-${y}`} x={10 + x * 18} y={8 + y * 16} width="16" height="14" rx="3" fill={`hsl(${hue} 70% ${t === 9 ? 60 : 28}%)`} opacity={t === 9 ? 1 : 0.55} />;
                }),
              )}
            </svg>
            <p className="text-xs text-slate-500">Highlighted: one wavefront (t = 9).</p>
          </Card>
          <Card title="Relation to the research paper">
            <p className="text-sm text-slate-400">
              NeuroCompress is <em>inspired by</em> “A Learned Pixel-by-Pixel Lossless Image Compression Method with 59K Parameters and Parallel Decoding” (Gumus &amp; Kamisli). It is <strong className="text-slate-200">not a reproduction</strong> of that work: the architecture, parameter counts (0.6k–18.8k here), training data and results are different and have not been compared with the paper's.
            </p>
          </Card>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <Card title="Training">
          <p className="text-sm text-slate-400">
            Models are trained with <span className="font-mono">backend/neurocompress/train.py</span>: pure NumPy, manual back-propagation and Adam, minimising the discretised-logistic negative log-likelihood (bits/sample), then quantised to fixed point. Training images are synthetic textures plus the small set of sample photos shipped with scikit-image / scikit-learn; three photos are held out and used to report honest numbers on the <Link to="/models" className="text-accent-cyan underline">Model Lab</Link>. Point <span className="font-mono">--data-dir</span> at your own images to train on your data.
          </p>
        </Card>
        <Card title="Limitations">
          <ul className="list-disc space-y-1 pl-5 text-sm text-slate-400">
            <li>The models are tiny and trained on little data; lossless WebP often wins on photographs.</li>
            <li>Pure NumPy / Python: encoding and decoding take seconds for images of around a megapixel, which is why uploads are capped (default 1,048,576 px).</li>
            <li>8-bit grayscale and RGB only; alpha is discarded and 16-bit data is reduced, with a warning.</li>
            <li>Practical size should include the weight file (shown as “+ model”); for a handful of small images the weights outweigh the savings.</li>
            <li>A stream can only be decoded by the same weight file (checked through a model id).</li>
          </ul>
        </Card>
      </div>
    </>
  );
}
