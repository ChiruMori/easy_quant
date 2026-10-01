import { useState } from "react"
import { Link, useLocation, useNavigate } from "react-router-dom"

import { useAuthentication } from "@/app/providers"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

export function LoginPage() {
  const { login } = useAuthentication()
  const navigate = useNavigate()
  const location = useLocation()
  const [error, setError] = useState("")
  const [pending, setPending] = useState(false)
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>登录Easy Quant 易量化平台</CardTitle>
          <CardDescription>使用管理员初始化账号或受邀账号登录。</CardDescription>
        </CardHeader>
        <form
          onSubmit={async (event) => {
            event.preventDefault()
            setPending(true)
            setError("")
            const data = new FormData(event.currentTarget)
            try {
              await login(String(data.get("username")), String(data.get("password")))
              navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true })
            } catch (reason) {
              setError(reason instanceof Error ? reason.message : "登录失败")
            } finally {
              setPending(false)
            }
          }}
        >
          <CardContent>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="username">用户名</FieldLabel>
                <Input id="username" name="username" autoComplete="username" required />
              </Field>
              <Field>
                <FieldLabel htmlFor="password">密码</FieldLabel>
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  required
                />
              </Field>
              {error && (
                <Alert variant="destructive">
                  <AlertTitle>无法登录</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </FieldGroup>
          </CardContent>
          <CardFooter className="mt-8 flex flex-col items-stretch gap-3">
            <Button type="submit" disabled={pending}>
              {pending ? "登录中…" : "登录"}
            </Button>
            <Button variant="link" asChild>
              <Link to="/register">使用邀请码注册</Link>
            </Button>
          </CardFooter>
        </form>
      </Card>
    </main>
  )
}
