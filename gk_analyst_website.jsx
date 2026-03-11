export default function GKAnalysisCoachWebsite() {

  const services = [
    {
      title: "Match Goalkeeper Analysis",
      desc: "Full match goalkeeper performance analysis including positioning, decision making, distribution, and key moments with clear feedback.",
    },
    {
      title: "Training Session Analysis",
      desc: "Professional evaluation of goalkeeper training sessions focusing on technique, footwork, handling, and movement efficiency.",
    },
    {
      title: "Individual Development Plan (IDP)",
      desc: "Structured goalkeeper development plans used by professional academies to accelerate goalkeeper progress.",
    },
    {
      title: "Club Recruitment Analysis",
      desc: "Objective goalkeeper performance reports designed for clubs and academies during recruitment or trial periods.",
    },
  ];

  const achievements = [
    "University Top Team Goalkeeper Coach",
    "Developed 4 Professional Football Players",
    "Assistant Goalkeeper Coach at a J-League Top Division Club",
    "Goalkeeper Performance Analyst",
    "Experience working with international players",
    "Modern European-style goalkeeper development methodology",
  ];

  const pricing = [
    {
      name: "Goalkeeper Analysis",
      price: "Consultation",
      desc: "Match or training analysis services. The scope and price depend on the project and level of detail required.",
    },
    {
      name: "Club / Academy Analysis",
      price: "Consultation",
      desc: "Performance analysis support for clubs or academies including recruitment analysis and goalkeeper development reports.",
    },
    {
      name: "Individual Development Plan",
      price: "Consultation",
      desc: "Professional goalkeeper development plans tailored to the player’s level, goals, and training environment.",
    },
  ];

  return (
    <div className="min-h-screen bg-black text-white">

      {/* HERO */}
      <section className="relative border-b border-yellow-500/20">
        <div className="mx-auto max-w-7xl px-6 py-24 lg:px-12">
          <div className="grid gap-12 lg:grid-cols-2 lg:items-center">

            <div>
              <div className="mb-4 inline-flex rounded-full border border-yellow-500/40 bg-yellow-500/10 px-4 py-1 text-sm text-yellow-400">
                Professional Goalkeeper Analysis
              </div>

              <h1 className="text-5xl font-bold leading-tight">
                Yasuto Hoshiko
                <br />
                <span className="text-yellow-400">GK Analysis Coach</span>
              </h1>

              <p className="mt-6 max-w-xl text-lg text-neutral-300">
                Professional goalkeeper analysis designed for modern football. Helping goalkeepers, coaches, and clubs understand performance and accelerate development through clear and objective feedback.
              </p>

              <div className="mt-8 flex gap-4">
                <a
                  href="#services"
                  className="rounded-xl bg-yellow-400 px-6 py-3 font-semibold text-black"
                >
                  View Services
                </a>

                <a
                  href="#contact"
                  className="rounded-xl border border-yellow-400 px-6 py-3 font-semibold text-yellow-400"
                >
                  Contact
                </a>
              </div>
            </div>

            <div className="rounded-3xl border border-yellow-500/20 bg-neutral-900 p-10">
              <h3 className="text-xl font-semibold text-yellow-400">Specialist Focus</h3>
              <ul className="mt-6 space-y-3 text-neutral-300">
                <li>• Goalkeeper Match Analysis</li>
                <li>• Tactical Decision Evaluation</li>
                <li>• Distribution Analysis</li>
                <li>• Modern Goalkeeper Development</li>
              </ul>
            </div>

          </div>
        </div>
      </section>


      {/* SERVICES */}
      <section id="services" className="mx-auto max-w-7xl px-6 py-24 lg:px-12">

        <h2 className="text-4xl font-bold">Services</h2>

        <div className="mt-10 grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          {services.map((service) => (
            <div
              key={service.title}
              className="rounded-2xl border border-yellow-500/20 bg-neutral-900 p-6"
            >
              <h3 className="text-xl font-semibold text-yellow-400">{service.title}</h3>
              <p className="mt-3 text-sm text-neutral-300">{service.desc}</p>
            </div>
          ))}
        </div>

      </section>


      {/* ACHIEVEMENTS */}
      <section className="border-y border-yellow-500/20 bg-neutral-950">

        <div className="mx-auto max-w-7xl px-6 py-24 lg:px-12">

          <h2 className="text-4xl font-bold">Experience & Approach</h2>

          <p className="mt-4 max-w-3xl text-neutral-400">
            Professional background built through goalkeeper coaching, performance analysis, and international football environments. Full CV and professional history are available upon request.
          </p>

          <div className="mt-10 grid gap-6 md:grid-cols-2">
            {achievements.map((item) => (
              <div
                key={item}
                className="rounded-2xl border border-yellow-500/20 bg-neutral-900 p-6"
              >
                {item}
              </div>
            ))}
          </div>

        </div>

      </section>


      {/* PRICING */}
      <section className="mx-auto max-w-7xl px-6 py-24 lg:px-12">

        <h2 className="text-4xl font-bold">Analysis Packages</h2>

        <div className="mt-12 grid gap-8 md:grid-cols-3">
          {pricing.map((plan) => (
            <div
              key={plan.name}
              className="rounded-3xl border border-yellow-500/20 bg-neutral-900 p-8"
            >
              <h3 className="text-2xl font-semibold text-yellow-400">{plan.name}</h3>

              <p className="mt-4 text-4xl font-bold">{plan.price}</p>

              <p className="mt-4 text-neutral-300">{plan.desc}</p>
            </div>
          ))}
        </div>

      </section>


      {/* CONTACT */}
      <section id="contact" className="border-t border-yellow-500/20 bg-black">

        <div className="mx-auto max-w-4xl px-6 py-24 text-center">

          <h2 className="text-4xl font-bold">Contact</h2>

          <p className="mt-6 text-neutral-300">
            For goalkeeper analysis requests, collaboration with clubs, or goalkeeper development inquiries, please contact directly.
          </p>

          <div className="mt-10 space-y-4 text-lg">
            <p>Email: yasutohoshiko1986@gmail.com</p>
            <p>Instagram / X / LinkedIn</p>
          </div>

        </div>

      </section>


    </div>
  );
}
