import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

export function Forbidden() {
  return (
    <Alert variant="destructive">
      <AlertTitle>无权访问</AlertTitle>
      <AlertDescription>此页面需要管理员权限，或资源不属于当前用户。</AlertDescription>
    </Alert>
  )
}
