import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type {
  MethodBreakdown,
  StatusBreakdown,
  TopProduct,
  TrendPoint,
} from '../types';
import { EmptyState, money, titleCase } from './UI';

/* Muted bronze leads; the rest are warm neutral shades. No chromatic accents. */
const COLORS = ['#936b52', '#252421', '#77736b', '#a8a297', '#c9c3b6', '#5d5a54'];

const BRONZE = '#936b52';
const CHARCOAL = '#252421';
const NEUTRAL = '#77736b';
const GRID = '#e5e1d8';
const HOVER = '#efebe3';

const AXIS = { fontSize: 11, fill: NEUTRAL };

function compactMoney(value: number, currency: string): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency,
    notation: 'compact',
    maximumFractionDigits: 1,
  }).format(value);
}

function ChartEmpty({ label }: { label: string }) {
  return <EmptyState title="No data yet" description={label} />;
}

const tooltipStyle = {
  background: '#ffffff',
  borderRadius: 8,
  border: `1px solid ${GRID}`,
  boxShadow: '0 8px 24px rgba(37, 36, 33, 0.10)',
  color: CHARCOAL,
  fontSize: 12,
};

export function SalesTrendChart({
  data,
  currency = 'INR',
  height = 300,
}: {
  data: TrendPoint[];
  currency?: string;
  height?: number;
}) {
  if (!data?.length) return <ChartEmpty label="Sales trends will appear once invoices are created." />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="period" tick={AXIS} axisLine={false} tickLine={false} dy={8} />
        <YAxis
          tick={AXIS}
          axisLine={false}
          tickLine={false}
          width={58}
          tickFormatter={(value: number) => compactMoney(value, currency)}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(value) => money(Number(value), currency)}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        <Area
          type="monotone"
          dataKey="sales"
          name="Sales"
          stroke={BRONZE}
          strokeWidth={2}
          fill={BRONZE}
          fillOpacity={0.12}
          activeDot={{ r: 4 }}
        />
        <Area
          type="monotone"
          dataKey="collections"
          name="Collections"
          stroke={NEUTRAL}
          strokeWidth={2}
          fill={NEUTRAL}
          fillOpacity={0.08}
          activeDot={{ r: 4 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function SalesBarChart({
  data,
  currency = 'INR',
  height = 320,
}: {
  data: TrendPoint[];
  currency?: string;
  height?: number;
}) {
  if (!data?.length) return <ChartEmpty label="Sales data for the selected period is empty." />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={4}>
        <CartesianGrid vertical={false} stroke={GRID} />
        <XAxis dataKey="period" tick={AXIS} axisLine={false} tickLine={false} dy={8} />
        <YAxis
          tick={AXIS}
          axisLine={false}
          tickLine={false}
          width={58}
          tickFormatter={(value: number) => compactMoney(value, currency)}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          cursor={{ fill: HOVER }}
          formatter={(value) => money(Number(value), currency)}
        />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />
        <Bar dataKey="sales" name="Sales" fill={BRONZE} radius={[3, 3, 0, 0]} maxBarSize={26} />
        <Bar
          dataKey="collections"
          name="Collections"
          fill={NEUTRAL}
          radius={[3, 3, 0, 0]}
          maxBarSize={26}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function PaymentMethodsChart({
  data,
  currency = 'INR',
  height = 280,
}: {
  data: MethodBreakdown[];
  currency?: string;
  height?: number;
}) {
  if (!data?.length) return <ChartEmpty label="Payment methods will appear after the first collection." />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          dataKey="amount"
          nameKey="method"
          cx="50%"
          cy="46%"
          innerRadius={58}
          outerRadius={86}
          paddingAngle={2}
          stroke="#ffffff"
          strokeWidth={2}
        >
          {data.map((entry, index) => (
            <Cell key={`${entry.method}-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={tooltipStyle}
          formatter={(value) => money(Number(value), currency)}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 12 }}
          formatter={(value) => titleCase(String(value))}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

export function StatusBreakdownChart({
  data,
  currency = 'INR',
  height = 260,
}: {
  data: StatusBreakdown[];
  currency?: string;
  height?: number;
}) {
  if (!data?.length) return <ChartEmpty label="Invoice status breakdown is unavailable." />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        layout="vertical"
        margin={{ top: 4, right: 24, left: 8, bottom: 0 }}
        barCategoryGap={14}
      >
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis
          type="number"
          tick={AXIS}
          axisLine={false}
          tickLine={false}
          tickFormatter={(value: number) => compactMoney(value, currency)}
        />
        <YAxis
          type="category"
          dataKey="status"
          tick={AXIS}
          axisLine={false}
          tickLine={false}
          width={100}
          tickFormatter={(value: string) => titleCase(value)}
        />
        <Tooltip
          contentStyle={tooltipStyle}
          cursor={{ fill: HOVER }}
          formatter={(value) => money(Number(value), currency)}
        />
        <Bar dataKey="amount" name="Amount" radius={[0, 3, 3, 0]} maxBarSize={20}>
          {data.map((entry, index) => (
            <Cell key={`${entry.status}-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function TopProductsChart({
  data,
  currency = 'INR',
  height = 300,
}: {
  data: TopProduct[];
  currency?: string;
  height?: number;
}) {
  const rows = data?.slice(0, 6) ?? [];
  if (!rows.length) return <ChartEmpty label="Top products will appear once sales are recorded." />;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={rows}
        layout="vertical"
        margin={{ top: 4, right: 24, left: 8, bottom: 0 }}
        barCategoryGap={12}
      >
        <CartesianGrid horizontal={false} stroke={GRID} />
        <XAxis
          type="number"
          tick={AXIS}
          axisLine={false}
          tickLine={false}
          tickFormatter={(value: number) => compactMoney(value, currency)}
        />
        <YAxis
          type="category"
          dataKey="name"
          tick={AXIS}
          axisLine={false}
          tickLine={false}
          width={110}
          tickFormatter={(value: string) =>
            value.length > 16 ? `${value.slice(0, 15)}…` : value
          }
        />
        <Tooltip
          contentStyle={tooltipStyle}
          cursor={{ fill: HOVER }}
          formatter={(value) => money(Number(value), currency)}
        />
        <Bar dataKey="revenue" name="Revenue" fill={CHARCOAL} radius={[0, 3, 3, 0]} maxBarSize={18} />
      </BarChart>
    </ResponsiveContainer>
  );
}
