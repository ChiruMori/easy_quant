import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorState, LoadingState } from "@/components/app-shell"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

import { createInvitation, listInvitations } from "../api"

export function InvitationsPage() {
  const client = useQueryClient()
  const query = useQuery({ queryKey: ["admin", "invitations"], queryFn: listInvitations })
  const [token, setToken] = useState("")
  if (query.isLoading) return <LoadingState label="正在加载邀请码" />
  if (query.error) return <ErrorState title="无法加载邀请码" message={query.error.message} />
  return (
    <div className="flex flex-col gap-5">
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>签发邀请码</CardTitle>
          <CardDescription>邀请码有效期 7 天、只能使用一次，明文仅在签发时展示。</CardDescription>
        </CardHeader>
        <CardContent>
          {token ? (
            <Alert>
              <AlertTitle>请立即复制邀请码</AlertTitle>
              <AlertDescription className="font-mono break-all">{token}</AlertDescription>
            </Alert>
          ) : (
            <p className="text-sm text-muted-foreground">尚未签发新邀请码。</p>
          )}
        </CardContent>
        <CardFooter>
          <Button
            onClick={async () => {
              const invitation = await createInvitation()
              setToken(invitation.token)
              await client.invalidateQueries({ queryKey: ["admin", "invitations"] })
            }}
          >
            签发邀请码
          </Button>
        </CardFooter>
      </Card>
      <div>
        <h2 className="text-lg font-semibold">签发记录</h2>
        <ul className="mt-3 flex flex-col gap-2">
          {query.data?.map((item) => (
            <li className="flex items-center justify-between rounded-md border p-3" key={item.id}>
              <span>
                {item.id} · 有效期至 {new Date(item.expires_at).toLocaleString()}
              </span>
              <Badge variant="secondary">{item.used_at ? "已使用" : "未使用"}</Badge>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
