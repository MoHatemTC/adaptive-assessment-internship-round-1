"use client";

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
} from "recharts";

import type { DimensionRadarPoint } from "@/lib/report-api";

export interface RadarChartProps {
  dimensions: DimensionRadarPoint[];
}

export function SkillRadarChart({ dimensions }: RadarChartProps) {
  const data = dimensions.map((dim) => ({
    dimension: dim.label,
    score: dim.score ?? 0,
    fullMark: 10,
  }));

  return (
    <div className="h-80 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="75%">
          <PolarGrid stroke="#D8DDF0" />
          <PolarAngleAxis
            dataKey="dimension"
            tick={{ fill: "#343434", fontSize: 12 }}
          />
          <PolarRadiusAxis
            angle={90}
            domain={[0, 10]}
            tick={{ fill: "#6B7280", fontSize: 10 }}
          />
          <Radar
            name="Score"
            dataKey="score"
            stroke="#004EFF"
            fill="#004EFF"
            fillOpacity={0.35}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
