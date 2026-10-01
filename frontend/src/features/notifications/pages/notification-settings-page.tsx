import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import { ErrorState, LoadingState } from "@/components/app-shell"
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
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { localizedLabel } from "@/lib/labels"

import { addSubscription, listDeliveries, listSubscriptions, updateSubscription } from "../api"

export function NotificationSettingsPage() {
  const client = useQueryClient()
  const subscriptions = useQuery({
    queryKey: ["notifications", "subscriptions"],
    queryFn: listSubscriptions,
  })
  const deliveries = useQuery({
    queryKey: ["notifications", "deliveries"],
    queryFn: listDeliveries,
  })
  const [channel, setChannel] = useState("ntfy")
  if (subscriptions.isLoading || deliveries.isLoading)
    return <LoadingState label="正在加载通知设置" />
  if (subscriptions.error || deliveries.error)
    return (
      <ErrorState
        title="无法加载通知设置"
        message={(subscriptions.error ?? deliveries.error)?.message ?? "未知错误"}
      />
    )
  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold">通知设置</h1>
        <p className="text-muted-foreground">
          实盘产生建议时可通过一个或多个渠道通知；平台不会自动下单。
        </p>
      </div>
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>添加通知渠道</CardTitle>
          <CardDescription>邮件填写收件地址；ntfy 填写主题名称或完整主题地址。</CardDescription>
        </CardHeader>
        <form
          onSubmit={async (event) => {
            event.preventDefault()
            const form = event.currentTarget
            const data = new FormData(form)
            await addSubscription(channel, String(data.get("destination")))
            form.reset()
            await client.invalidateQueries({ queryKey: ["notifications"] })
          }}
        >
          <CardContent>
            <FieldGroup>
              <Field>
                <FieldLabel>渠道</FieldLabel>
                <Select value={channel} onValueChange={setChannel}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectGroup>
                      <SelectItem value="email">邮件</SelectItem>
                      <SelectItem value="ntfy">ntfy</SelectItem>
                    </SelectGroup>
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="destination">通知目标</FieldLabel>
                <Input id="destination" name="destination" required />
              </Field>
            </FieldGroup>
          </CardContent>
          <CardFooter>
            <Button type="submit">添加渠道</Button>
          </CardFooter>
        </form>
      </Card>
      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">已配置渠道</h2>
        {subscriptions.data?.map((item) => (
          <Field orientation="horizontal" className="max-w-2xl rounded-md border p-4" key={item.id}>
            <div className="flex-1">
              <p className="font-medium">{localizedLabel(item.channel)}</p>
              <p className="text-sm text-muted-foreground">{item.destination}</p>
            </div>
            <Switch
              checked={item.enabled}
              onCheckedChange={async (enabled) => {
                await updateSubscription(item.id, enabled)
                await client.invalidateQueries({ queryKey: ["notifications", "subscriptions"] })
              }}
            />
          </Field>
        ))}
      </section>
      <section>
        <h2 className="text-lg font-semibold">最近投递</h2>
        {deliveries.data?.length ? (
          <div className="mt-2 flex flex-col gap-2">
            {deliveries.data.map((delivery) => (
              <div
                className="flex max-w-2xl items-center justify-between rounded-md border p-3"
                key={delivery.id}
              >
                <span>{localizedLabel(delivery.channel)}</span>
                <span className="text-sm text-muted-foreground">
                  {localizedLabel(delivery.status)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">尚无投递记录</p>
        )}
      </section>
    </div>
  )
}
