import { Request, Response } from "express";
import bukit_merah_data from "../sample-data/bukit-merah.json";
import bukit_panjang_data from "../sample-data/bukit-panjang.json";
import choa_chu_kang_data from "../sample-data/choa-chu-kang.json";
import clementi_data from "../sample-data/clementi.json";
import woodlands_data from "../sample-data/woodlands.json";

export const getRecommednations = (req: Request, res: Response) => {
    const town = req.query.town
    if(town == "BUKIT MERAH"){
        res.json(bukit_merah_data);
    }
     if(town == "BUKIT PANJANG"){
        res.json(bukit_panjang_data);
    }
     if(town == "CHOA CHU KANG"){
        res.json(choa_chu_kang_data);
    }
    if(town == "CLEMENTI"){
        res.json(clementi_data);
    }
    if(town == "WOODLANDS"){
        res.json(woodlands_data);
    }

   return res.status(404).json({
      error: "User not found"
    });
};