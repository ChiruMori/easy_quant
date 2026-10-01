import { useState } from "react"
import { Link, useNavigate } from "react-router-dom"

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
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"

import { acceptInvitation } from "../api"

export function RegisterPage() {
  const navigate = useNavigate()
  const [error, setError] = useState("")
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/30 p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>使用邀请码注册</CardTitle>
          <CardDescription>邀请码由平台管理员签发且只能使用一次。</CardDescription>
        </CardHeader>
        <form
          onSubmit={async (event) => {
            event.preventDefault()
            const data = new FormData(event.currentTarget)
            setError("")
            try {
              await acceptInvitation(
                String(data.get("token")),
                String(data.get("username")),
                String(data.get("password")),
              )
              navigate("/login", { replace: true })
            } catch (reason) {
              setError(reason instanceof Error ? reason.message : "注册失败")
            }
          }}
        >
          <CardContent>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="token">邀请码</FieldLabel>
                <Input id="token" name="token" required />
              </Field>
              <Field>
                <FieldLabel htmlFor="new-username">用户名</FieldLabel>
                <Input id="new-username" name="username" required />
              </Field>
              <Field>
                <FieldLabel htmlFor="new-password">密码</FieldLabel>
                <Input id="new-password" name="password" type="password" minLength={12} required />
                <FieldDescription>至少 12 个字符。</FieldDescription>
              </Field>
              {error && (
                <Alert variant="destructive">
                  <AlertTitle>无法注册</AlertTitle>
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
            </FieldGroup>
          </CardContent>
          <CardFooter className="flex flex-col items-stretch gap-3">
            <Button type="submit">创建账号</Button>
            <Button variant="link" asChild>
              <Link to="/login">返回登录</Link>
            </Button>
          </CardFooter>
        </form>
      </Card>
    </main>
  )
}
