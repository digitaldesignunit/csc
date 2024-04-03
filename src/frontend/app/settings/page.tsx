import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div className="grid gap-[32px] m-4">
      <Card>
        <CardHeader>
          <CardTitle>Settings</CardTitle>
          <CardDescription>These are the Settings</CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}