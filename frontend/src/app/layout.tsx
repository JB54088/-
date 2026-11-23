import "./globals.css";

export const metadata = { title: "观云春 · 企业客户资产经营平台", description: "企业客户资产经营平台 V1" };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
