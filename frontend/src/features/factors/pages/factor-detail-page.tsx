interface FactorDetail {
  key: string
  name: string
  description: string
  parameters: Record<string, string>
  output: string
  example: string
}

export function FactorDetailPage({ factor }: { factor: FactorDetail }) {
  return (
    <article className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">{factor.name}</h1>
      <p>{factor.description}</p>
      <h2>参数</h2>
      <dl>
        {Object.entries(factor.parameters).map(([key, value]) => (
          <div key={key}>
            <dt>
              <code>{key}</code>
            </dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
      <h2>输出</h2>
      <p>{factor.output}</p>
      <h2>示例</h2>
      <pre>{factor.example}</pre>
    </article>
  )
}
