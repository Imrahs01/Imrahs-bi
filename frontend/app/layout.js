export const metadata = {
  title: "Vantage — Your Solution for Business Growth",
  description: "Upload your business data and get instant KPIs, risk signals, and an AI analyst.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, background: "#0D1117", color: "#EAEDF2",
        fontFamily: "Inter, system-ui, sans-serif" }}>
        {children}
      </body>
    </html>
  );
}
