import Image from "next/image";
import Link from "next/link";

export default function HomePage() {
  return (
    <>
      <header className="fixed top-0 z-50 w-full border-b border-border-base bg-surface/80 backdrop-blur-md transition-colors duration-200">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-8">
          <span className="text-headline-md tracking-tight text-primary">
            Masaar
          </span>
          <nav className="hidden items-center gap-6 md:flex">
            <Link
              href="#how-it-works"
              className="text-label-md text-on-surface-variant transition-colors hover:text-primary"
            >
              How it works
            </Link>
            <Link
              href="#dimensions"
              className="text-label-md text-on-surface-variant transition-colors hover:text-primary"
            >
              Dimensions
            </Link>
            <Link
              href="#tools"
              className="text-label-md text-on-surface-variant transition-colors hover:text-primary"
            >
              Tools
            </Link>
            <button className="rounded-lg bg-primary px-6 py-2 text-label-md text-on-primary shadow-sm transition-colors hover:bg-primary-hover">
              Get Started
            </button>
          </nav>
        </div>
      </header>

      <main className="overflow-hidden pt-24 pb-section">
        {/* HERO */}
        <section className="mx-auto flex max-w-7xl flex-col items-center px-8 pb-section pt-section text-center">
          <h1 className="mb-md max-w-4xl text-headline-display tracking-tight text-on-surface">
            Adaptive Assessments Powered by Intelligent AI
          </h1>
          <p className="mb-lg max-w-2xl text-body-lg text-on-surface-variant">
            Masaar dynamically adjusts difficulty in real-time, probing deeper
            into a candidate&apos;s potential through adaptive questioning.
          </p>
          <div className="flex flex-col gap-sm sm:flex-row">
            <button className="flex h-11 items-center justify-center rounded-lg bg-primary px-8 text-label-lg text-on-primary shadow-sm transition-colors hover:bg-primary-hover">
              Create Assessment
            </button>
            <button className="flex h-11 items-center justify-center rounded-lg border border-primary bg-transparent px-8 text-label-lg text-primary transition-colors hover:bg-surface-accent">
              Start Assessment
            </button>
          </div>
          <div className="relative mt-section aspect-[21/9] w-full max-w-5xl overflow-hidden rounded-xl border border-border-base bg-surface-container-lowest shadow-[0_4px_40px_rgba(0,0,0,0.08)]">
            <Image
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuCkY96THvFZ5Zy9osSXvKDNbZKXBD_4ZLShZP7tj5gFPC6Kp7jE5sLqH5vO1s0hpjWTZuTsWstTVoHC-4roK1JbIqZpt92tCK2R3FgqJ_eIHjwyRa4kU2hu8-fak60h26shVWY7fNBH1RkHc5iBjjZDAXG-l9L_Mu5pbP4zywDECUnBOGTvBNweZVhwrEBeqcFq0H5nX-o3sPxIjopd-q4yJ6rWI5hleKLMXOuTCear5nOseBsGEOxil5i3mquHeLO89DpTJ23XlLI"
              alt="A clean, professional UI mockup of a product chat interface for a SaaS platform called Masaar."
              fill
              className="object-cover"
              sizes="(max-width: 1280px) 100vw, 1280px"
            />
          </div>
        </section>

        {/* HOW IT WORKS */}
        <section
          id="how-it-works"
          className="mx-auto max-w-7xl border-t border-border-base px-8 py-section"
        >
          <div className="mb-xl text-center">
            <h2 className="text-headline-lg tracking-tight text-on-surface">
              How It Works
            </h2>
            <p className="mt-xs text-body-md text-on-surface-variant">
              A seamless flow from creation to insight.
            </p>
          </div>
          <div className="relative grid grid-cols-1 gap-gutter md:grid-cols-3">
            <div className="absolute left-1/6 right-1/6 top-12 z-0 hidden h-[1px] bg-border-base md:block" />
            {/* Step 1 */}
            <div className="relative z-10 flex flex-col items-center rounded-xl border border-border-base bg-surface-container-lowest p-md text-center shadow-sm">
              <div className="mb-sm flex h-16 w-16 items-center justify-center rounded-full border border-border-base bg-surface-accent text-primary shadow-sm">
                <span
                  className="material-symbols-outlined text-[32px]"
                  style={{ fontVariationSettings: "'FILL' 0" }}
                >
                  target
                </span>
              </div>
              <h3 className="mb-xs text-title-md text-on-surface">
                1. Define Objective
              </h3>
              <p className="text-body-sm text-on-surface-variant">
                Admin describes what to test, AI builds the blueprint.
              </p>
            </div>
            {/* Step 2 */}
            <div className="relative z-10 flex flex-col items-center rounded-xl border border-border-base bg-surface-container-lowest p-md text-center shadow-sm">
              <div className="mb-sm flex h-16 w-16 items-center justify-center rounded-full border border-border-base bg-surface-accent text-primary shadow-sm">
                <span
                  className="material-symbols-outlined text-[32px]"
                  style={{ fontVariationSettings: "'FILL' 0" }}
                >
                  network_node
                </span>
              </div>
              <h3 className="mb-xs text-title-md text-on-surface">
                2. Adaptive Intake
              </h3>
              <p className="text-body-sm text-on-surface-variant">
                Learner receives a link and takes the adaptive exam.
              </p>
            </div>
            {/* Step 3 */}
            <div className="relative z-10 flex flex-col items-center rounded-xl border border-border-base bg-surface-container-lowest p-md text-center shadow-sm">
              <div className="mb-sm flex h-16 w-16 items-center justify-center rounded-full border border-border-base bg-surface-accent text-primary shadow-sm">
                <span
                  className="material-symbols-outlined text-[32px]"
                  style={{ fontVariationSettings: "'FILL' 0" }}
                >
                  radar
                </span>
              </div>
              <h3 className="mb-xs text-title-md text-on-surface">
                3. Insightful Reporting
              </h3>
              <p className="text-body-sm text-on-surface-variant">
                Admin receives a radar report visualizing strengths and gaps.
              </p>
            </div>
          </div>
        </section>

        {/* DIMENSIONS ANALYZED */}
        <section
          id="dimensions"
          className="mx-auto max-w-7xl border-t border-border-base bg-surface-container-low/30 px-8 py-section"
        >
          <div className="mb-xl">
            <h2 className="text-headline-lg tracking-tight text-on-surface">
              Dimensions Analyzed
            </h2>
            <p className="mt-xs text-body-md text-on-surface-variant">
              Comprehensive evaluation across five key vectors.
            </p>
          </div>
          <div className="hide-scrollbar flex snap-x snap-mandatory gap-sm overflow-x-auto pb-8">
            <DimensionCard
              icon="psychology"
              title="Thinking"
              description="Logical reasoning and problem-solving capabilities."
            />
            <DimensionCard
              icon="forum"
              title="Soft Skills"
              description="Communication and interpersonal effectiveness."
            />
            <DimensionCard
              icon="work_history"
              title="Work Ethic"
              description="Reliability, discipline, and execution standards."
            />
            <DimensionCard
              icon="computer"
              title="Digital & AI"
              description="Technical literacy and AI tool proficiency."
            />
            <DimensionCard
              icon="trending_up"
              title="Growth Mindset"
              description="Adaptability and continuous learning potential."
            />
          </div>
        </section>

        {/* TOOLS */}
        <section
          id="tools"
          className="mx-auto max-w-7xl border-t border-border-base px-8 py-section"
        >
          <div className="mb-xl text-center">
            <h2 className="text-headline-lg tracking-tight text-on-surface">
              Assessment Tools
            </h2>
            <p className="mt-xs text-body-md text-on-surface-variant">
              Diverse methodologies to capture a complete profile.
            </p>
          </div>
          <div className="grid grid-cols-1 gap-gutter sm:grid-cols-2 lg:grid-cols-4">
            <ToolCard
              icon="list_alt"
              title="MCQ"
              description="Objectively scored multiple-choice questions dynamically adjusted for difficulty."
            />
            <ToolCard
              icon="mic"
              title="Voice Interview"
              description="Verbal responses analyzed for clarity, depth, and communication style."
            />
            <ToolCard
              icon="account_tree"
              title="Diagram"
              description="Visual reasoning and structural analysis tasks to evaluate systemic thinking."
            />
            <ToolCard
              icon="terminal"
              title="Code Execution"
              description="Sandboxed coding challenges for verified technical proficiency evaluation."
            />
          </div>
        </section>
      </main>

      <footer className="w-full border-t border-border-base bg-surface-container-lowest py-lg">
        <div className="mx-auto flex max-w-7xl flex-col items-center gap-sm px-8 text-center md:flex-row md:justify-between md:text-left">
          <p className="text-body-sm font-medium text-on-surface-variant">
            Masaar &mdash; Adaptive Assessment Platform
          </p>
          <div className="flex gap-sm">
            <Link
              href="#"
              className="text-label-sm text-outline transition-colors hover:text-primary"
            >
              Privacy
            </Link>
            <Link
              href="#"
              className="text-label-sm text-outline transition-colors hover:text-primary"
            >
              Terms
            </Link>
          </div>
        </div>
      </footer>
    </>
  );
}

function DimensionCard({
  icon,
  title,
  description,
}: {
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <div className="min-w-[280px] flex-1 snap-start rounded-[24px] border border-border-base bg-surface-container-lowest p-md shadow-sm transition-transform duration-300 hover:-translate-y-1">
      <div className="mb-sm flex h-10 w-10 items-center justify-center rounded-lg bg-surface-accent text-primary">
        <span
          className="material-symbols-outlined"
          style={{ fontVariationSettings: "'FILL' 0" }}
        >
          {icon}
        </span>
      </div>
      <h3 className="mb-xs text-title-md text-on-surface">{title}</h3>
      <p className="text-body-sm text-on-surface-variant">{description}</p>
    </div>
  );
}

function ToolCard({
  icon,
  title,
  description,
}: {
  icon: string;
  title: string;
  description: string;
}) {
  return (
    <div className="group flex flex-col rounded-[24px] border border-border-base bg-surface-container-lowest p-md shadow-sm">
      <div className="mb-sm flex items-center gap-xs">
        <span
          className="material-symbols-outlined text-primary transition-transform group-hover:scale-110"
          style={{ fontVariationSettings: "'FILL' 0" }}
        >
          {icon}
        </span>
        <h3 className="text-title-md text-on-surface">{title}</h3>
      </div>
      <p className="flex-grow text-body-sm text-on-surface-variant">
        {description}
      </p>
    </div>
  );
}
