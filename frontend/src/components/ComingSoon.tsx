import { Result } from "antd";
import type { ReactNode } from "react";

export default function ComingSoon({
  title,
  icon,
  description,
}: {
  title: string;
  icon: ReactNode;
  description: string;
}) {
  return (
    <Result
      icon={icon}
      title={title}
      subTitle={description}
      style={{ marginTop: 60 }}
    />
  );
}
